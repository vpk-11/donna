"""False-pass and false-fail rate of the claim verifier on a labeled set.

Usage: python scripts/judge_eval.py [model ...]     (default: the configured agent model)
Each case in tests/data/judge_labeled.json is a reply plus the turn's tool trace, labeled pass (supported)
or fail (unsupported claim). Needs a running LLM; no DB or Redis. Writes results/judge-eval-<timestamp>.md.
"""
import asyncio
import json
import statistics
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

from config import settings  # noqa: E402
from intelligence.claim_judge import verify_reply  # noqa: E402


async def run(model: str, cases: list[dict]) -> str:
    settings.judge_model, settings.llm_max_tokens = model, 2000
    ok = fails = 0
    false_fail, false_pass, lat = [], [], []
    for c in cases:
        t0 = time.perf_counter()
        passed = await verify_reply(c["reply"], c["trace"])
        lat.append(time.perf_counter() - t0)
        if c["label"] == "pass" and not passed:
            false_fail.append(c["reply"])
        if c["label"] == "fail" and passed:
            false_pass.append(c["reply"])
        ok += c["label"] == "pass"
        fails += c["label"] == "fail"
    lines = [
        f"| {model} | {len(false_fail)}/{ok} | {len(false_pass)}/{fails} | {statistics.median(lat):.1f} | {max(lat):.1f} |",
        "",
        f"False fails ({model}): " + ("; ".join(map(repr, false_fail)) or "none"),
        f"False passes ({model}): " + ("; ".join(map(repr, false_pass)) or "none"),
    ]
    return "\n".join(lines)


def main() -> None:
    cases = json.loads((ROOT / "tests" / "data" / "judge_labeled.json").read_text())
    # Production skips the judge when a tool wrote the reply (ClientAgent: `authored`), so those cases are unreachable.
    total = len(cases)
    cases = [c for c in cases if not any(isinstance(t["result"], dict) and t["result"].get("confirmation")
                                         for t in c["trace"])]
    models = sys.argv[1:] or [settings.donna_model or settings.llm_model]
    head = [
        f"Judge eval {datetime.now():%Y-%m-%d %H:%M}, tests/data/judge_labeled.json ({len(cases)} of {total} cases reachable in production)",
        f"Conditions: model under test is the judge (judge_model overridden), LLM_MAX_TOKENS=2000, judge_timeout_s={settings.judge_timeout_s}, "
        "errors and timeouts count as fail (fail-closed)",
        "",
        "| model | false fails (supported replies blocked) | false passes (unsupported replies sent) | median call s | max call s |",
        "|---|---|---|---|---|",
    ]
    body = [asyncio.run(run(m, cases)) for m in models]
    # table rows first, details after
    rows = [b.split("\n\n")[0] for b in body]
    details = [b.split("\n\n")[1] for b in body]
    text = "\n".join(head + rows + [""] + details)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"judge-eval-{datetime.now():%Y%m%d-%H%M%S}.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
