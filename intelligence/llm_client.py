import litellm
from config import settings


class LLMCallError(Exception):
    pass


async def _complete(messages: list[dict], model: str | None, **extra):
    try:
        return await litellm.acompletion(
            model=model or settings.donna_model or settings.llm_model,
            messages=messages,
            api_base=settings.llm_api_base or None,
            api_key=settings.llm_api_key or None,
            temperature=settings.llm_temperature,
            max_tokens=settings.llm_max_tokens,
            **extra,
        )
    except Exception as e:
        raise LLMCallError(f"LLM call failed: {e}") from e


async def call_llm(
    messages: list[dict],
    response_format: dict | None = None,
    model: str | None = None,
) -> str:
    response = await _complete(
        messages, model, **({"response_format": response_format} if response_format else {}),
    )
    return response.choices[0].message.content.strip()


async def call_llm_tools(messages: list[dict], tools: list[dict], model: str | None = None) -> dict:
    """One tool-calling step. Returns the assistant message as a dict (content, tool_calls)."""
    response = await _complete(messages, model, **({"tools": tools} if tools else {}))
    return response.choices[0].message.model_dump()
