"""Reliability table over tests/live per model.

Usage: python scripts/eval.py [model ...]      (default: $DONNA_EVAL_MODELS, comma separated)
Models are LiteLLM names, e.g. ollama_chat/gpt-oss:20b. Runs in a scratch copy of the repo with a
throwaway Redis on port 6390, because the suite drops tables and flushes Redis.
Writes results/eval-<timestamp>.md and prints it.
"""
import json
import math
import os
import shutil
import statistics
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
from config import settings  # noqa: E402
REDIS_PORT = os.environ.get("DONNA_EVAL_REDIS_PORT", "6390")


def run_model(model: str, scratch: Path) -> list[dict]:
    out = scratch / "eval.jsonl"
    out.unlink(missing_ok=True)
    env = {
        **os.environ, "DONNA_LIVE": "1", "DONNA_MODEL": model, "DONNA_EVAL_OUT": str(out),
        "REDIS_PORT": REDIS_PORT, "ADMIN_PHONE": "+15559990000", "LLM_MAX_TOKENS": os.environ.get("LLM_MAX_TOKENS", "2000"),
    }
    if not model.startswith("ollama"):  # hosted provider: LiteLLM routes by prefix, the Ollama base URL must go
        env["LLM_API_BASE"] = ""
        env["LLM_API_KEY"] = ""  # an explicit key would shadow the provider's own variable (e.g. GROQ_API_KEY)
    subprocess.run([sys.executable, "-m", "pytest", "tests/live", "-q", "-p", "no:cacheprovider"],
                   cwd=scratch / "repo", env=env, check=False)
    return [json.loads(line) for line in out.read_text().splitlines()] if out.exists() else []


def p95(xs: list[float]) -> float:
    """Nearest-rank 95th percentile."""
    xs = sorted(xs)
    return xs[max(0, math.ceil(0.95 * len(xs)) - 1)]


def row(model: str, results: list[dict]) -> str:
    turns = [t for r in results for t in r["turns"]]
    lat = [t["latency_s"] for t in turns]
    passed = sum(r["outcome"] == "passed" for r in results)
    failed = ", ".join(r["test"] for r in results if r["outcome"] != "passed") or "-"
    if not turns:
        return f"| {model} | {passed}/{len(results)} | - | - | - | {failed} |"
    return (f"| {model} | {passed}/{len(results)} | {statistics.mean(t['tools'] for t in turns):.2f} "
            f"| {statistics.median(lat):.1f} | {p95(lat):.1f} | {failed} |")


def main() -> None:
    models = sys.argv[1:] or [m for m in os.environ.get("DONNA_EVAL_MODELS", "").split(",") if m]
    if not models:
        sys.exit("no models: pass them as args or set DONNA_EVAL_MODELS")
    scratch = Path(tempfile.mkdtemp(prefix="donna-eval-"))
    shutil.copytree(ROOT, scratch / "repo", ignore=shutil.ignore_patterns(
        ".git", "donna.db", "graphify-out", "__pycache__", "results"))
    redis = subprocess.Popen(["redis-server", "--port", REDIS_PORT, "--save", ""], stdout=subprocess.DEVNULL)
    try:
        rows = [row(m, run_model(m, scratch)) for m in models]
    finally:
        redis.terminate()
        shutil.rmtree(scratch, ignore_errors=True)
    table = "\n".join([
        f"Eval {datetime.now():%Y-%m-%d %H:%M}, tests/live",
        f"Conditions: LLM_MAX_TOKENS={os.environ.get('LLM_MAX_TOKENS', '2000')}, claim_verifier={'on' if settings.claim_verifier else 'off'} (settings default), judge_model={settings.judge_model or 'agent model'}, "
        "local Ollama, tool calls/turn counts every tool call in a handle_message turn",
        "",
        "| model | passed | tool calls/turn | median turn s | p95 turn s | failed |",
        "|---|---|---|---|---|---|",
        *rows,
    ])
    (ROOT / "results").mkdir(exist_ok=True)
    (ROOT / "results" / f"eval-{datetime.now():%Y%m%d-%H%M%S}.md").write_text(table + "\n")
    print(table)


if __name__ == "__main__":
    main()
