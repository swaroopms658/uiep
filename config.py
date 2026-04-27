from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    SECRET_KEY: str
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days

    DATABASE_URL: str = "sqlite:///./upi_tracker.db"
    DB_POOL_SIZE: int = 10
    DB_MAX_OVERFLOW: int = 20
    SQLALCHEMY_ECHO: bool = False

    DEBUG: bool = False

    GROQ_API_KEY: str  # comma-separated list of keys for rotation

    @property
    def groq_api_keys(self) -> list[str]:
        return [k.strip() for k in self.GROQ_API_KEY.split(",") if k.strip()]

    REDIS_URL: str = "redis://localhost:6379/0"
    CACHE_TTL_SECONDS: int = 300  # 5 minutes

    # Comma-separated list of allowed origins for CORS
    CORS_ORIGINS: str = "http://localhost:19006,http://localhost:3000"

    # Storage: "local" or "s3"
    STORAGE_TYPE: str = "local"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_BUCKET_NAME: str = ""
    AWS_REGION: str = "us-east-1"
    CLOUDFLARE_ACCOUNT_ID: str = ""

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def normalize_database_url(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        if value.startswith("postgresql://") and "+psycopg" not in value:
            return value.replace("postgresql://", "postgresql+psycopg://", 1)
        if value.startswith("postgres://"):
            return value.replace("postgres://", "postgresql+psycopg://", 1)
        return value

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
