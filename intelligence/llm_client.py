import asyncio
import logging

import litellm
from config import settings


logger = logging.getLogger(__name__)


class LLMCallError(Exception):
    pass


async def _complete(messages: list[dict], model: str | None, **extra):
    """One completion with a per-attempt timeout and a bounded number of attempts."""
    for attempt in range(1, settings.llm_max_attempts + 1):
        try:
            return await asyncio.wait_for(
                litellm.acompletion(
                    model=model or settings.donna_model or settings.llm_model,
                    messages=messages,
                    api_base=settings.llm_api_base or None,
                    api_key=settings.llm_api_key or None,
                    temperature=settings.llm_temperature,
                    max_tokens=settings.llm_max_tokens,
                    timeout=settings.llm_timeout_s,
                    **extra,
                ),
                settings.llm_timeout_s,
            )
        except Exception as e:
            if attempt == settings.llm_max_attempts:
                raise LLMCallError(f"LLM call failed after {attempt} attempts: {e!r}") from e
            logger.warning(f"llm attempt {attempt} failed: {e!r}")
            await asyncio.sleep(settings.llm_retry_backoff_s * 2 ** (attempt - 1))


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
