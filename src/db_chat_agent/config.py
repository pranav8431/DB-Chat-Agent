import os
from dataclasses import dataclass

from dotenv import load_dotenv


load_dotenv()


@dataclass
class Settings:
    llm_provider: str = os.getenv("LLM_PROVIDER", "ollama")
    llm_base_url: str = os.getenv("LLM_BASE_URL", "http://localhost:11434")
    llm_model: str = os.getenv("LLM_MODEL", "gemma3:8b")
    llm_api_key: str | None = os.getenv("LLM_API_KEY") or None
    max_result_rows: int = int(os.getenv("MAX_RESULT_ROWS", "200"))
    llm_timeout_seconds: int = int(os.getenv("LLM_TIMEOUT_SECONDS", "120"))
    llm_max_tokens: int = int(os.getenv("LLM_MAX_TOKENS", "256"))
    sql_retry_attempts: int = int(os.getenv("SQL_RETRY_ATTEMPTS", "3"))
    conversation_history_turns: int = int(os.getenv("CONVERSATION_HISTORY_TURNS", "3"))
