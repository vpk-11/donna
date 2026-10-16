import json
import os
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM — local Ollama by default. Swappable to any litellm-supported provider
    # via env vars alone (LLM_MODEL/LLM_API_BASE/LLM_API_KEY), no code change needed.
    llm_model: str = "ollama_chat/qwen2.5:7b-instruct"
    llm_api_base: str = "http://localhost:11434"
    llm_api_key: str = ""
    llm_temperature: float = 0.2
    llm_max_tokens: int = 500
    # Per-call model override (e.g. a different model for one-off testing).
    # Was an undocumented os.environ.get("DONNA_MODEL") read in llm_client.py;
    # now a real Settings field, still read from the DONNA_MODEL env var.
    donna_model: str = ""
    # Per-attempt LLM timeout, bounded retries with exponential backoff, scanner timeout.
    llm_timeout_s: float = 120.0
    llm_max_attempts: int = 3
    turn_timeout_s: float = 180.0  # whole tool loop of one agent turn
    llm_retry_backoff_s: float = 1.0
    scanner_timeout_s: float = 30.0
    send_timeout_s: float = 10.0  # one outbound message over the transport
    # Post-response claim verifier (intelligence/claim_judge.py). Empty model = same as the agent's.
    claim_verifier: bool = True
    judge_model: str = ""
    judge_timeout_s: float = 30.0  # gpt-oss:20b p95 turn is ~26s; the judge defaults to the agent's own model

    # Provider bootstrap
    admin_phone: str
    admin_name: str
    business_type: str = "trainer"
    location_type: str = "mobile"
    auto_book: bool = False
    buffer_mins: int = 15
    working_hours: str = '{"mon":["09:00","18:00"],"tue":["09:00","18:00"],"wed":["09:00","18:00"],"thu":["09:00","18:00"],"fri":["09:00","18:00"]}'

    # Optional
    google_maps_api_key: str = ""
    linq_api_token: str = ""
    linq_phone_number: str = ""
    linq_developer_phone: str = ""

    port: int = 8000

    class Config:
        env_file = None
        extra = "ignore"


settings = Settings()

_BUSINESS_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config", "business.json")
_business_config: dict | None = None


def load_business_config() -> dict:
    """Load config/business.json once, cache in-process. Static file, no
    conversational onboarding — see .claude/CLAUDE.md."""
    global _business_config
    if _business_config is None:
        with open(_BUSINESS_CONFIG_PATH) as f:
            _business_config = json.load(f)
    return _business_config
