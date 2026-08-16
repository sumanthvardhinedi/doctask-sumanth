from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = (
        "postgresql+psycopg://superdocs:superdocs_dev_password@localhost:5432/superdocs"
    )

    superdocs_base_url: str = "https://api.superdocs.app"
    superdocs_api_key: str = ""
    uploads_root: str = "uploads"
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"


settings = Settings()


def cors_origin_list() -> list[str]:
    return [origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()]