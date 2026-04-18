import json
import logging
from config import settings
from models.schemas import IntentResult
from intelligence.prompts import INTENT_PARSER_SYSTEM, INTENT_PARSER_USER_TEMPLATE, INTENT_RETRY_USER_TEMPLATE

logger = logging.getLogger(__name__)

FALLBACK_RESULT = IntentResult(
    intent="UNKNOWN",
    entities={},
    needs_clarification=False,
    clarification_question=None,
)


async def _call_llm(system: str, user: str) -> str:
    import litellm
    response = await litellm.acompletion(
        model=settings.llm_model,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        api_base=settings.llm_api_base or None,
        api_key=settings.llm_api_key or None,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
    )
    return response.choices[0].message.content.strip()


def _parse_json_response(raw: str) -> IntentResult | None:
    try:
        start = raw.index("{")
        end = raw.rindex("}") + 1
        data = json.loads(raw[start:end])
        return IntentResult(**data)
    except Exception:
        return None


async def parse_intent(
    message: str,
    role: str,
    context: dict,
    last_donna_message: str,
) -> IntentResult:
    user_prompt = INTENT_PARSER_USER_TEMPLATE.format(
        last_donna_message=last_donna_message or "",
        context_json=json.dumps(context),
        role=role,
        message=message,
    )
    try:
        raw = await _call_llm(INTENT_PARSER_SYSTEM, user_prompt)
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
        raw = await _call_llm(INTENT_PARSER_SYSTEM, retry_prompt)
        result = _parse_json_response(raw)
        if result:
            logger.info(f"Parsed intent (retry): {result.intent}")
            return result
    except Exception as e:
        logger.warning(f"Intent parse attempt 2 failed: {e}")

    logger.warning(f"Falling back to UNKNOWN for: {message[:60]}")
    return FALLBACK_RESULT
