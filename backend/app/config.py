from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="AGENTRANK_", extra="ignore")

    # Defaults run without Docker: SQLite + audits executed in-process.
    # With `docker compose up`, set DATABASE_URL to Postgres and USE_QUEUE=true.
    database_url: str = "sqlite:///./agentrank.db"
    redis_url: str = "redis://localhost:6379/0"
    use_queue: bool = False

    storage_dir: Path = Path("./storage")
    max_pages: int = 25
    request_timeout_s: float = 20.0
    crawl_delay_s: float = 0.5
    user_agent: str = "AgentRankBot/0.1 (+https://github.com/agentrank; audit crawler)"
    render_js: bool = True
    cookie_secure: bool = False  # set true behind HTTPS

    # LLM: any OpenAI-compatible chat completions endpoint. Groq for the prototype.
    llm_base_url: str = "https://api.groq.com/openai/v1"
    llm_model: str = "openai/gpt-oss-120b"
    llm_fallback_model: str | None = "openai/gpt-oss-20b"  # used when llm_model's daily quota is spent
    llm_api_key: str | None = Field(default=None, validation_alias=AliasChoices("AGENTRANK_LLM_API_KEY", "GROQ_API_KEY"))

    # Agent task testing (FR-20..22). Defaults fit Groq's free tier (8K tokens/min, 200K/day);
    # the requirements call for 3 runs per task once budget allows.
    agent_tests_enabled: bool = True
    agent_max_tasks: int = 2
    agent_runs_per_task: int = 2
    agent_max_steps: int = 8
    agent_model: str | None = None  # defaults to llm_model

    # AI visibility (FR-23..25). Each answer with web search costs ~6K tokens on Groq, so the defaults are
    # small; each model has its own rate limit, so providers are queried in parallel.
    visibility_enabled: bool = True
    visibility_prompts: int = 6
    visibility_samples: int = 1
    visibility_models: list[str] = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
    visibility_token_budget: int = 40_000  # per model per audit; remaining prompts are skipped once spent

    # PageSpeed Insights works without a key at a low shared quota; a key raises it.
    pagespeed_api_key: str | None = None
    pagespeed_enabled: bool = True
    link_check_limit: int = 40


settings = Settings()
