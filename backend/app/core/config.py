from urllib.parse import quote_plus

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Event Pilot API"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    llm_provider: str = "azure"
    model_deployment: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment_name: str | None = Field(default=None, validation_alias=AliasChoices("AZURE_OPENAI_DEPLOYMENT_NAME", "AZURE_OPENAI_CHAT_DEPLOYMENT", "AZURE_OPENAI_DEPLOYMENT"))
    azure_openai_embedding_deployment: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://us.cloud.langfuse.com"
    langfuse_host: str | None = None
    langfuse_tracing_environment: str = "development"
    # Optional: enables "Open in Langfuse" deep links in the step drawer.
    langfuse_project_id: str | None = None
    db_user: str | None = None
    db_password: str | None = None
    db_host: str | None = None
    db_port: int = 5432
    db_name: str | None = None
    collection_name: str = "eventpilot_knowledge"
    rag_embedding_dimensions: int = 1536
    rag_top_k: int = 4
    rag_min_relevance_score: float = 0.55

    # Planning runs (streaming, checkpoints and recovery).
    mcp_url: str = "http://127.0.0.1:8000/mcp"
    data_dir: str = "data"
    max_parallel_llm_calls: int = 3
    max_step_attempts: int = 3
    max_replans: int = 2  # review-driven re-plans of the affected specialists
    # Comma-separated MCP tool names whose first call in every run fails, e.g.
    # "venue_search". Used to demonstrate the recovery flow.
    eventpilot_fail_once: str = ""
    # MCP tools: free web services (Open-Meteo, OpenStreetMap Nominatim, OSRM demo).
    # Set FREE_APIS_ENABLED=false to use only the bundled offline data.
    free_apis_enabled: bool = True
    # Added to the User-Agent, as Nominatim's usage policy asks: e.g. "you@example.com".
    http_contact: str = ""
    http_timeout_s: float = 6.0
    tool_timeout_s: float = 25.0
    max_tool_calls_per_run: int = 40
    tool_cache_ttl_s: int = 600
    # Abuse protection. Limits apply per client to write requests; LLM endpoints get their own budget.
    rate_limit_enabled: bool = True
    rate_limit_writes_per_minute: int = 60
    rate_limit_llm_per_minute: int = 12
    rate_limit_llm_per_day: int = 300
    # Only behind a trusted reverse proxy: use X-Forwarded-For as the client address.
    trust_forwarded_for: bool = False
    max_body_bytes: int = 262_144
    max_chat_chars: int = 1_000
    # Optional prices (USD per 1K tokens) for the usage line; 0 hides cost.
    llm_cost_per_1k_input: float = 0.0
    llm_cost_per_1k_output: float = 0.0

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def azure_openai_enabled(self) -> bool:
        return all((
            self.azure_openai_api_key,
            self.azure_openai_endpoint,
            self.azure_openai_deployment_name,
        ))

    @property
    def azure_embeddings_enabled(self) -> bool:
        return bool(self.azure_openai_api_key and self.azure_openai_endpoint and self.azure_openai_embedding_deployment)

    @property
    def postgres_enabled(self) -> bool:
        return bool(self.db_user and self.db_password and self.db_host and self.db_name)

    @property
    def postgres_dsn(self) -> str:
        if not self.postgres_enabled:
            raise RuntimeError("PostgreSQL configuration is incomplete")
        return f"postgresql://{quote_plus(self.db_user or '')}:{quote_plus(self.db_password or '')}@{self.db_host}:{self.db_port}/{self.db_name}"

    @property
    def rag_enabled(self) -> bool:
        return self.postgres_enabled and self.azure_embeddings_enabled

    @property
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def resolved_langfuse_base_url(self) -> str:
        """Support the legacy LANGFUSE_HOST name already used by local setups."""
        return self.langfuse_host or self.langfuse_base_url

    @property
    def fail_once_tools(self) -> set[str]:
        return {name.strip() for name in self.eventpilot_fail_once.split(",") if name.strip()}


settings = Settings()
