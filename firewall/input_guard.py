import re
import logging
from llm_guard.input_scanners import PromptInjection, BanTopics, TokenLimit
from llm_guard.input_scanners.prompt_injection import MatchType
from firewall.rules import (
    BANNED_INPUT_TOPICS,
    BAN_TOPICS_THRESHOLD,
    TOKEN_LIMIT,
    IDENTITY_SPOOF_PATTERNS,
    INPUT_SCANNER_FAIL_MODE,
    SYSTEM_PROMPT_PATTERNS,
    EXFILTRATION_PATTERNS,
    REDIRECT_OUT_OF_SCOPE,
    SCHEDULING_VOCAB,
    MAX_PLAIN_REQUEST_WORDS,
    REDIRECT_MEDICAL,
    BLOCK_GENERIC_RESPONSE,
)
from firewall.timeout import scan_with_timeout
from config import settings
from models.schemas import FirewallResult

logger = logging.getLogger(__name__)

_injection_scanner = PromptInjection(match_type=MatchType.FULL)
_topic_scanner = BanTopics(topics=BANNED_INPUT_TOPICS, threshold=BAN_TOPICS_THRESHOLD)
_token_scanner = TokenLimit(limit=TOKEN_LIMIT)
_system_prompt_patterns = [re.compile(p, re.IGNORECASE) for p in SYSTEM_PROMPT_PATTERNS]
_identity_spoof_patterns = [re.compile(p, re.IGNORECASE) for p in IDENTITY_SPOOF_PATTERNS]
# Impersonating the provider by name ("It's <name> here", "this is <name>").
_provider_first = (settings.admin_name.split() or [""])[0]
if _provider_first:
    _name = re.escape(_provider_first)
    _identity_spoof_patterns += [
        re.compile(rf"\b(i'?m|i am|this is|it'?s) {_name}\b", re.IGNORECASE),
        re.compile(rf"\b{_name} (here|speaking)\b", re.IGNORECASE),
    ]
_exfiltration_patterns = [re.compile(p, re.IGNORECASE) for p in EXFILTRATION_PATTERNS]


_PLAIN_CHARS = re.compile(r"[A-Za-z0-9:'.,!?\- ]+")  # spaces only: no newlines or other whitespace
_TIME_TOKEN = re.compile(r"\d{1,2}(:\d{2})?(am|pm|st|nd|rd|th)?")


def is_plain_scheduling_request(message: str) -> bool:
    """True if the message is plain ASCII text whose every word is scheduling vocabulary or a day/time number.
    Any other character (non-ASCII letters, CJK, emoji, symbols, newlines) disqualifies it, so nothing the
    tokenizer would skip over can carry a payload."""
    if not _PLAIN_CHARS.fullmatch(message):
        return False
    words = re.findall(r"[a-z0-9:']+", message.lower())
    return 0 < len(words) <= MAX_PLAIN_REQUEST_WORDS and all(
        w in SCHEDULING_VOCAB or _TIME_TOKEN.fullmatch(w) for w in words
    )


def _scanner_failed(name: str, exc: Exception, phone: str) -> FirewallResult | None:
    """Fail-closed scanners return a block result; fail-open scanners return None."""
    if INPUT_SCANNER_FAIL_MODE[name] == "open":
        logger.error("firewall.input.scanner_error %s: %s", name, exc, extra={"phone": phone})
        return None
    logger.error("firewall.input.fail_closed %s: %s", name, exc, extra={"phone": phone})
    return FirewallResult(
        action="block",
        threat="ScannerFailClosed",
        severity="high",
        redirect_message=BLOCK_GENERIC_RESPONSE,
        log_entry={"phone": phone, "scanner": name, "error": str(exc)},
    )


def scan_input(message: str, phone: str, is_admin: bool) -> FirewallResult:
    try:
        _, is_valid, _ = scan_with_timeout(_token_scanner, prompt=message)
        if not is_valid:
            logger.warning("firewall.input.token_limit", extra={"phone": phone})
            return FirewallResult(
                action="block",
                threat="TokenLimit",
                severity="medium",
                redirect_message=BLOCK_GENERIC_RESPONSE,
                log_entry={"phone": phone, "message_preview": message[:100]},
            )
    except Exception as exc:
        if failed := _scanner_failed("token_limit", exc, phone):
            return failed

    for pattern in _system_prompt_patterns:
        if pattern.search(message):
            logger.warning("firewall.input.system_prompt_extraction", extra={"phone": phone})
            return FirewallResult(
                action="block",
                threat="SystemPromptExtraction",
                severity="high",
                redirect_message=BLOCK_GENERIC_RESPONSE,
                log_entry={"phone": phone, "message_preview": message[:100]},
            )

    # The admin is the authenticated owner: the ML injection, topic and exfiltration checks
    # false-positive on ordinary commands ("yes, confirm it", "list my clients").
    if is_admin:
        return FirewallResult(action="pass")

    # Run specific identity spoof check before generic injection ML so that
    # more precise threat label wins when both would fire.
    if not is_admin:
        try:
            spoofed = any(p.search(message) for p in _identity_spoof_patterns)
        except Exception as exc:
            if failed := _scanner_failed("identity_spoof", exc, phone):
                return failed
        else:
            if spoofed:
                logger.warning("firewall.input.identity_spoof", extra={"phone": phone})
                return FirewallResult(
                    action="block",
                    threat="IdentitySpoofing",
                    severity="high",
                    redirect_message=BLOCK_GENERIC_RESPONSE,
                    log_entry={"phone": phone, "message_preview": message[:100]},
                )

    try:
        if not is_plain_scheduling_request(message):  # see SCHEDULING_VOCAB in rules.py
            _, is_valid, risk_score = scan_with_timeout(_injection_scanner, prompt=message)
            if not is_valid:
                logger.warning(
                    "firewall.input.prompt_injection",
                    extra={"phone": phone, "risk_score": risk_score},
                )
                return FirewallResult(
                    action="block",
                    threat="PromptInjection",
                    severity="high",
                    redirect_message=BLOCK_GENERIC_RESPONSE,
                    log_entry={"phone": phone, "risk_score": risk_score, "message_preview": message[:100]},
                )
    except Exception as exc:
        if failed := _scanner_failed("prompt_injection", exc, phone):
            return failed

    try:
        _, is_valid, topics_meta = scan_with_timeout(_topic_scanner, prompt=message)
        if not is_valid:
            topic_list = topics_meta if isinstance(topics_meta, list) else []
            redirect_msg = (
                REDIRECT_MEDICAL
                if any("medical" in t or "injury" in t for t in topic_list)
                else REDIRECT_OUT_OF_SCOPE
            )
            return FirewallResult(
                action="redirect",
                threat="BanTopics",
                severity="low",
                redirect_message=redirect_msg,
                log_entry={"phone": phone, "topics": topics_meta},
            )
    except Exception as exc:
        if failed := _scanner_failed("ban_topics", exc, phone):
            return failed

    for pattern in _exfiltration_patterns:
        if pattern.search(message):
            logger.warning("firewall.input.data_exfiltration", extra={"phone": phone})
            return FirewallResult(
                action="block",
                threat="DataExfiltration",
                severity="high",
                redirect_message=BLOCK_GENERIC_RESPONSE,
                log_entry={"phone": phone, "message_preview": message[:100]},
            )

    return FirewallResult(action="pass")
