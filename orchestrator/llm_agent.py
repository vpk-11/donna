import asyncio
import inspect
import json
import logging
from typing import Callable

from config import settings
from intelligence.llm_client import call_llm_tools

logger = logging.getLogger(__name__)

MAX_STEPS = 6

NONE = {"type": "object", "properties": {}}
DATE_TIME = {
    "date": {"type": "string", "description": "Date, e.g. 2026-09-22 or 'Monday'"},
    "time": {"type": "string", "description": "Time, e.g. '10:00' or '10am'"},
}


def obj(props: dict) -> dict:
    """JSON schema for an object whose properties are all required."""
    return {"type": "object", "properties": props, "required": list(props)}

def tool_specs(tools: dict[str, tuple[str, dict, Callable]]) -> list[dict]:
    return [
        {"type": "function", "function": {"name": n, "description": d, "parameters": p}}
        for n, (d, p, _) in tools.items()
    ]


async def _call_tool(tools: dict, name: str, raw) -> tuple[object, bool]:
    """Run one tool call. Returns (result, succeeded). A dict with `error` or booked=False is a failure."""
    if name not in tools:
        return {"error": f"unknown tool {name}"}, False
    fn = tools[name][2]
    try:
        args = json.loads(raw) if isinstance(raw, str) else dict(raw)
        try:
            inspect.signature(fn).bind(**args)
        except TypeError as e:
            return {"error": f"bad arguments: {e}"}, False
        out = fn(**args)
        result = await out if inspect.isawaitable(out) else out
    except Exception as e:
        logger.warning(f"agent tool {name} failed: {e}")
        return {"error": str(e)}, False
    failed = isinstance(result, dict) and (result.get("error") or result.get("booked") is False)
    return result, not failed


async def _run_loop(
    system: str,
    history: list[dict],
    user_text: str,
    tools: dict[str, tuple[str, dict, Callable]],
    calls_made: list[str] | None = None,
    trace: list[dict] | None = None,
    confirmations: list[str] | None = None,
) -> str:
    """Tool-use loop for one LLM agent. tools: name -> (description, json-schema params, callable)."""
    messages = [{"role": "system", "content": system}]
    for t in history:
        role = "assistant" if t["role"] in ("donna", "assistant") else "user"
        messages.append({"role": role, "content": t["content"]})
    messages.append({"role": "user", "content": user_text})
    specs = tool_specs(tools)

    retried = False
    confirmations = [] if confirmations is None else confirmations  # tool-authored text for state changes
    for _ in range(MAX_STEPS):
        msg = await call_llm_tools(messages, specs)
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text and not retried:  # reasoning models can spend the whole budget thinking
                retried = True
                messages.append({"role": "user", "content": "Reply now with your final text message."})
                continue
            return " ".join(confirmations) or text
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            raw = call["function"].get("arguments") or "{}"
            result, ok = await _call_tool(tools, name, raw)
            if ok and calls_made is not None:
                calls_made.append(name)
            if trace is not None:
                trace.append({"tool": name, "ok": ok, "result": result})
            if isinstance(result, dict) and result.get("confirmation") and not result.get("error"):
                confirmations.append(result["confirmation"])
            logger.info(f"agent.tool {name}({raw}) -> {json.dumps(result, default=str)[:300]}")
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": json.dumps(result, default=str),
            })
    return " ".join(confirmations)  # step cap: a state change that already happened must still reach the client


async def run_agent(*args, **kwargs) -> str:
    """Tool-use loop with a whole-turn deadline. On timeout, return any tool-authored confirmations
    already earned (a booking may have happened), else "" so callers send their fallback."""
    confirmations: list[str] = []
    try:
        return await asyncio.wait_for(_run_loop(*args, confirmations=confirmations, **kwargs), settings.turn_timeout_s)
    except asyncio.TimeoutError:
        logger.error(f"agent turn exceeded {settings.turn_timeout_s}s")
        return " ".join(confirmations)
