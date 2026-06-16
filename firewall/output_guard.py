import re
import logging
from llm_guard.output_scanners import Sensitive, BanTopics, NoRefusal
from firewall.rules import (
    BANNED_OUTPUT_TOPICS,
    BOOKING_CONFIRMATION_PATTERNS,
    BLOCK_GENERIC_RESPONSE,
)
from models.schemas import FirewallResult

logger = logging.getLogger(__name__)

_sensitive_scanner = Sensitive()
_topic_scanner = BanTopics(topics=BANNED_OUTPUT_TOPICS, threshold=0.75)
_refusal_scanner = NoRefusal()
_booking_patterns = [re.compile(p, re.IGNORECASE) for p in BOOKING_CONFIRMATION_PATTERNS]

_known_client_names: set[str] = set()


def register_client_names(names: list[str]) -> None:
    _known_client_names.update(n.lower() for n in names)


def scan_output(response: str, phone: str, tool_calls_made: list[str]) -> FirewallResult:
    try:
        _, is_valid, _ = _sensitive_scanner.scan(prompt="", output=response)
        if not is_valid:
            logger.warning("firewall.output.sensitive_data", extra={"phone": phone})
            return FirewallResult(
                action="block",
                threat="SensitiveData",
                severity="high",
                redirect_message=BLOCK_GENERIC_RESPONSE,
                log_entry={"phone": phone, "response_preview": response[:100]},
            )
    except Exception as exc:
        logger.error("firewall.output.scanner_error sensitive: %s", exc, extra={"phone": phone})

    try:
        _, is_valid, topics_meta = _topic_scanner.scan(prompt="", output=response)
        if not is_valid:
            logger.warning(
                "firewall.output.banned_topic",
                extra={"phone": phone, "topics": topics_meta},
            )
            return FirewallResult(
                action="block",
                threat="BannedOutputTopic",
                severity="high",
                redirect_message=BLOCK_GENERIC_RESPONSE,
                log_entry={"phone": phone, "topics": topics_meta},
            )
    except Exception as exc:
        logger.error("firewall.output.scanner_error ban_topics: %s", exc, extra={"phone": phone})

    booking_language_found = any(p.search(response) for p in _booking_patterns)
    if booking_language_found and "book_session" not in tool_calls_made:
        logger.error("firewall.output.booking_hallucination", extra={"phone": phone})
        return FirewallResult(
            action="block",
            threat="BookingHallucination",
            severity="high",
            redirect_message="Let me double-check on that and get back to you in a moment.",
            log_entry={
                "phone": phone,
                "tool_calls_made": tool_calls_made,
                "response_preview": response[:100],
            },
        )

    response_lower = response.lower()
    for name in _known_client_names:
        if name in response_lower:
            logger.error(
                "firewall.output.cross_client_leak",
                extra={"phone": phone, "leaked_name": name},
            )
            return FirewallResult(
                action="block",
                threat="CrossClientLeak",
                severity="high",
                redirect_message=BLOCK_GENERIC_RESPONSE,
                log_entry={"phone": phone, "leaked_name": name},
            )

    return FirewallResult(action="pass")
