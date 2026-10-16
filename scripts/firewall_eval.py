"""Labeled-set eval of the input firewall, swept over the prompt-injection threshold.

Usage: python scripts/firewall_eval.py [threshold ...]
Runs scan_input (client path) on tests/data/firewall_labeled.json. Needs no DB or Redis.
A message counts as blocked when action != "pass". Benign blocked = false blocks.
Writes results/firewall-eval-<timestamp>.md and prints it.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

import logging  # noqa: E402

logging.disable(logging.CRITICAL)

from llm_guard.input_scanners import PromptInjection  # noqa: E402
from llm_guard.input_scanners.prompt_injection import MatchType  # noqa: E402

from firewall import input_guard  # noqa: E402

THRESHOLDS = [0.5, 0.8, 0.92, 0.95, 0.98, 0.99, 0.995, 0.999]


def main() -> None:
    data = json.loads((ROOT / "tests" / "data" / "firewall_labeled.json").read_text())
    thresholds = [float(t) for t in sys.argv[1:]] or THRESHOLDS
    rows, benign_detail = [], {}
    for th in thresholds:
        input_guard._injection_scanner = PromptInjection(threshold=th, match_type=MatchType.FULL)
        res = {k: [input_guard.scan_input(m, "+15559990001", False) for m in msgs] for k, msgs in data.items()}
        blocked = {k: sum(r.action == "block" for r in v) for k, v in res.items()}
        redirected = sum(r.action == "redirect" for r in res["benign"])
        ml_only = sum(r.threat == "PromptInjection" for r in res["injection"] + res["spoof"] if r.action == "block")
        benign_detail[th] = [(m, r.threat) for m, r in zip(data["benign"], res["benign"]) if r.action == "block"]
        rows.append(
            f"| {th} | {blocked['injection']}/{len(data['injection'])} | {blocked['spoof']}/{len(data['spoof'])} "
            f"| {blocked['benign']}/{len(data['benign'])} | {redirected} | {ml_only} |"
        )
    out = [
        f"Firewall eval {datetime.now():%Y-%m-%d %H:%M}, tests/data/firewall_labeled.json",
        "Conditions: scan_input client path (is_admin=False), regex checks + ML scanners at their shipped settings, "
        "only the injection threshold varied; hand-written messages",
        "",
        "| injection threshold | injection blocked | spoof blocked | benign blocked (false) | benign redirected | blocks by ML scanner |",
        "|---|---|---|---|---|---|",
        *rows,
        "",
        "Benign messages blocked, per threshold:",
    ]
    for th, items in benign_detail.items():
        out.append(f"- {th}: " + ("; ".join(f"{m!r} ({t})" for m, t in items) or "none"))
    text = "\n".join(out)
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"firewall-eval-{datetime.now():%Y%m%d-%H%M%S}.md").write_text(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
