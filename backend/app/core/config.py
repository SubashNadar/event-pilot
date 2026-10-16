from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "EventPilot API"
    api_prefix: str = "/api/v1"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:5174,http://127.0.0.1:5174"
    llm_provider: str = "azure"
    model_deployment: str | None = None
    azure_openai_api_key: str | None = None
    azure_openai_endpoint: str | None = None
    azure_openai_api_version: str = "2024-10-21"
    azure_openai_deployment_name: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_base_url: str = "https://us.cloud.langfuse.com"
    langfuse_host: str | None = None
    langfuse_tracing_environment: str = "development"

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
    def langfuse_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)

    @property
    def resolved_langfuse_base_url(self) -> str:
        """Support the legacy LANGFUSE_HOST name already used by local setups."""
        return self.langfuse_host or self.langfuse_base_url


settings = Settings()
