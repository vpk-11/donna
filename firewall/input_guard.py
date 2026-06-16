import re
import logging
from llm_guard.input_scanners import PromptInjection, BanTopics, TokenLimit
from llm_guard.input_scanners.prompt_injection import MatchType
from firewall.rules import (
    BANNED_INPUT_TOPICS,
    BAN_TOPICS_THRESHOLD,
    TOKEN_LIMIT,
    IDENTITY_SPOOF_PATTERNS,
    SYSTEM_PROMPT_PATTERNS,
    EXFILTRATION_PATTERNS,
    REDIRECT_OUT_OF_SCOPE,
    REDIRECT_MEDICAL,
    BLOCK_GENERIC_RESPONSE,
)
from models.schemas import FirewallResult

logger = logging.getLogger(__name__)

_injection_scanner = PromptInjection(match_type=MatchType.FULL)
_topic_scanner = BanTopics(topics=BANNED_INPUT_TOPICS, threshold=BAN_TOPICS_THRESHOLD)
_token_scanner = TokenLimit(limit=TOKEN_LIMIT)
_system_prompt_patterns = [re.compile(p, re.IGNORECASE) for p in SYSTEM_PROMPT_PATTERNS]
_identity_spoof_patterns = [re.compile(p, re.IGNORECASE) for p in IDENTITY_SPOOF_PATTERNS]
_exfiltration_patterns = [re.compile(p, re.IGNORECASE) for p in EXFILTRATION_PATTERNS]


def scan_input(message: str, phone: str, is_admin: bool) -> FirewallResult:
    try:
        _, is_valid, _ = _token_scanner.scan(prompt=message)
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
        logger.error("firewall.input.scanner_error token_limit: %s", exc, extra={"phone": phone})

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

    # Run specific identity spoof check before generic injection ML so that
    # more precise threat label wins when both would fire.
    if not is_admin:
        for pattern in _identity_spoof_patterns:
            if pattern.search(message):
                logger.warning("firewall.input.identity_spoof", extra={"phone": phone})
                return FirewallResult(
                    action="block",
                    threat="IdentitySpoofing",
                    severity="high",
                    redirect_message=BLOCK_GENERIC_RESPONSE,
                    log_entry={"phone": phone, "message_preview": message[:100]},
                )

    try:
        _, is_valid, risk_score = _injection_scanner.scan(prompt=message)
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
        logger.error("firewall.input.scanner_error prompt_injection: %s", exc, extra={"phone": phone})

    try:
        _, is_valid, topics_meta = _topic_scanner.scan(prompt=message)
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
        logger.error("firewall.input.scanner_error ban_topics: %s", exc, extra={"phone": phone})

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
