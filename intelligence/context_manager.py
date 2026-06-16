import logging
from intelligence.llm_client import call_llm
from intelligence.prompts import SUMMARIZER_SYSTEM, SUMMARIZER_USER_TEMPLATE

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 20
HISTORY_TAIL_AFTER_SUMMARY = 5


def should_summarize(history: list[dict]) -> bool:
    return len(history) >= MAX_HISTORY_TURNS


async def summarize_conversation(
    history: list[dict],
    client_name: str,
    provider_name: str,
) -> str:
    if not history:
        return ""

    history_text = "\n".join(
        f"{'Donna' if t['role'] == 'donna' else client_name}: {t['content']}"
        for t in history
    )
    user_prompt = SUMMARIZER_USER_TEMPLATE.format(
        client_name=client_name,
        provider_name=provider_name,
        history=history_text,
    )
    try:
        summary = await call_llm(messages=[
            {"role": "system", "content": SUMMARIZER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ])
        logger.info(f"context_manager.summarize: {len(history)} turns → {len(summary)} chars")
        return summary.strip()
    except Exception as e:
        logger.warning(f"context_manager.summarize failed: {e}")
        return ""


def trim_history(history: list[dict], summary: str) -> list[dict]:
    tail = history[-HISTORY_TAIL_AFTER_SUMMARY:] if len(history) > HISTORY_TAIL_AFTER_SUMMARY else history
    summary_entry = {
        "role": "system",
        "content": f"[Conversation summary: {summary}]",
    }
    return [summary_entry] + tail


def build_context_from_summary(summary: str) -> list[dict]:
    if not summary:
        return []
    return [{
        "role": "system",
        "content": f"[Previous session summary: {summary}]",
    }]
