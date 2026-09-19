import inspect
import json
import logging
from typing import Callable

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


async def run_agent(
    system: str,
    history: list[dict],
    user_text: str,
    tools: dict[str, tuple[str, dict, Callable]],
    calls_made: list[str] | None = None,
) -> str:
    """Tool-use loop for one LLM agent. tools: name -> (description, json-schema params, callable)."""
    messages = [{"role": "system", "content": system}]
    for t in history:
        role = "assistant" if t["role"] in ("donna", "assistant") else "user"
        messages.append({"role": role, "content": t["content"]})
    messages.append({"role": "user", "content": user_text})
    specs = tool_specs(tools)

    retried = False
    for _ in range(MAX_STEPS):
        msg = await call_llm_tools(messages, specs)
        calls = msg.get("tool_calls") or []
        if not calls:
            text = (msg.get("content") or "").strip()
            if not text and not retried:  # reasoning models can spend the whole budget thinking
                retried = True
                continue
            return text
        messages.append({"role": "assistant", "content": msg.get("content") or "", "tool_calls": calls})
        for call in calls:
            name = call["function"]["name"]
            raw = call["function"].get("arguments") or "{}"
            result, ok = await _call_tool(tools, name, raw)
            if ok and calls_made is not None:
                calls_made.append(name)
            logger.info(f"agent.tool {name}({raw}) -> {json.dumps(result, default=str)[:300]}")
            messages.append({
                "role": "tool",
                "tool_call_id": call.get("id", name),
                "content": json.dumps(result, default=str),
            })
    return ""
