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


settings = Settings()