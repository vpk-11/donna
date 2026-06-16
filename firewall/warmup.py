import logging

logger = logging.getLogger(__name__)


def warmup_firewall() -> None:
    logger.info("firewall.warmup: loading prompt injection model...")
    from firewall.input_guard import _injection_scanner
    _injection_scanner.scan(prompt="warmup")
    logger.info("firewall.warmup: done")
