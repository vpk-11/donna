import json
import logging
from models.schemas import IntentResult
from intelligence.prompts import INTENT_PARSER_SYSTEM, INTENT_PARSER_USER_TEMPLATE, INTENT_RETRY_USER_TEMPLATE
from intelligence.llm_client import call_llm

logger = logging.getLogger(__name__)

FALLBACK_RESULT = IntentResult(
    intent="UNKNOWN",
    entities={},
    confidence=0.0,
)


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior conversation)"
    lines = []
    for turn in history[-6:]:  # last 6 turns for intent context
        label = "User" if turn["role"] == "user" else "Donna"
        lines.append(f"{label}: {turn['content']}")
    return "\n".join(lines)


def _parse_json_response(raw: str) -> IntentResult | None:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        if isinstance(data.get("entities"), dict):
            data["entities"] = {k: (v if v is not None else "") for k, v in data["entities"].items()}
        return IntentResult(
            intent=data.get("intent", "UNKNOWN"),
            entities=data.get("entities", {}),
            confidence=float(data.get("confidence", 0.5)),
        )
    except Exception:
        return None


async def parse_intent(
    message: str,
    role: str,
    context: dict,
    last_donna_message: str,
    history: list[dict] | None = None,
) -> IntentResult:
    clean_context = {k: v for k, v in context.items() if not k.startswith("_")}

    user_prompt = INTENT_PARSER_USER_TEMPLATE.format(
        history=_format_history(history or []),
        last_donna_message=last_donna_message or "",
        context_json=json.dumps(clean_context),
        role=role,
        message=message,
    )
    try:
        raw = await call_llm(messages=[
            {"role": "system", "content": INTENT_PARSER_SYSTEM},
            {"role": "user", "content": user_prompt},
        ])
        result = _parse_json_response(raw)
        if result:
            logger.info(f"Parsed intent: {result.intent} for role={role}")
            return result
    except Exception as e:
        logger.warning(f"Intent parse attempt 1 failed: {e}")

    retry_prompt = INTENT_RETRY_USER_TEMPLATE.format(
        role=role,
        message=message,
        last_donna_message=last_donna_message or "",
    )
    try:
        raw = await call_llm(messages=[
            {"role": "system", "content": INTENT_PARSER_SYSTEM},
            {"role": "user", "content": retry_prompt},
        ])
        result = _parse_json_response(raw)
        if result:
            logger.info(f"Parsed intent (retry): {result.intent}")
            return result
    except Exception as e:
        logger.warning(f"Intent parse attempt 2 failed: {e}")

    logger.warning(f"Falling back to UNKNOWN for: {message[:60]}")
    return FALLBACK_RESULT
