import logging
from config import settings
from intelligence.prompts import RESPONSE_GENERATOR_SYSTEM_TEMPLATE, RESPONSE_GENERATOR_USER_TEMPLATE

logger = logging.getLogger(__name__)


def _format_history(history: list[dict]) -> str:
    if not history:
        return "(no prior conversation)\n"
    lines = []
    for turn in history[-8:]:  # last 8 turns for response context
        label = "User" if turn["role"] == "user" else "Donna"
        lines.append(f"{label}: {turn['content']}")
    return "\n".join(lines) + "\n"


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


async def generate_response(
    situation: str,
    recipient: str,
    provider_name: str,
    business_type: str,
    history: list[dict] | None = None,
    client_profile: str | None = None,
) -> str:
    system = RESPONSE_GENERATOR_SYSTEM_TEMPLATE.format(
        provider_name=provider_name,
        business_type=business_type,
    )
    profile_block = f"Client profile: {client_profile}\n\n" if client_profile else ""
    user = RESPONSE_GENERATOR_USER_TEMPLATE.format(
        profile_block=profile_block,
        history=_format_history(history or []),
        situation=situation,
        recipient=recipient,
    )
    try:
        raw = await _call_llm(system, user)
        return raw.strip()
    except Exception as e:
        logger.error(f"Response generation failed: {e}")
        return "Got it - I'll take care of that."
