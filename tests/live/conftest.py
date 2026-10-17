"""Records per-test outcome, turn latency and tool calls to $DONNA_EVAL_OUT (jsonl) when set."""
import json
import os
import time

import pytest

OUT = os.environ.get("DONNA_EVAL_OUT")
_turns: list[dict] = []


def _write(row: dict) -> None:
    with open(OUT, "a") as f:
        f.write(json.dumps(row) + "\n")


@pytest.fixture(autouse=True)
def _record_turns(monkeypatch):
    if not OUT:
        yield
        return
    import orchestrator.llm_agent as llm_agent
    from orchestrator.central import CentralOrchestrator

    _turns.clear()
    state = {"tools": 0}
    real_call, real_handle = llm_agent._call_tool, CentralOrchestrator.handle_message

    async def counted(tools, name, raw):
        state["tools"] += 1
        return await real_call(tools, name, raw)

    async def timed(self, phone, text, db):
        state["tools"] = 0
        t0 = time.perf_counter()
        try:
            return await real_handle(self, phone, text, db)
        finally:
            _turns.append({"latency_s": time.perf_counter() - t0, "tools": state["tools"]})

    monkeypatch.setattr(llm_agent, "_call_tool", counted)
    monkeypatch.setattr(CentralOrchestrator, "handle_message", timed)
    yield


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    rep = outcome.get_result()
    if OUT and rep.when == "call":
        _write({"test": item.name, "outcome": rep.outcome, "turns": list(_turns)})
