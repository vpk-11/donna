import litellm
from config import settings


class LLMCallError(Exception):
    pass


async def call_llm(
    messages: list[dict],
    response_format: dict | None = None,
    model: str | None = None,
) -> str:
    resolved_model = model or settings.donna_model or settings.llm_model
    try:
        kwargs = dict(
            model=resolved_model,
            messages=messages,
            api_base=settings.llm_api_base or None,
            api_key=settings.llm_api_key or None,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        if response_format:
            kwargs["response_format"] = response_format
        response = await litellm.acompletion(**kwargs)
        return response.choices[0].message.content.strip()
    except Exception as e:
        raise LLMCallError(f"LLM call failed: {e}") from e


async def call_llm_tools(messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
    """One tool-calling step. Returns the assistant message as a dict (content, tool_calls)."""
    resolved_model = model or settings.donna_model or settings.llm_model
    try:
        response = await litellm.acompletion(
            model=resolved_model,
            messages=messages,
            **({"tools": tools} if tools else {}),
            api_base=settings.llm_api_base or None,
            api_key=settings.llm_api_key or None,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
        )
        return response.choices[0].message.model_dump()
    except Exception as e:
        raise LLMCallError(f"LLM tool call failed: {e}") from e
