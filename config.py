from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    SECRET_KEY: str = "super_secret_temporary_key_for_development"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    DATABASE_URL: str = "sqlite:///./upi_tracker.db"
    DEBUG: bool = True
    GROQ_API_KEY: str = "fallback_key"

    model_config = SettingsConfigDict(env_file=".env")

settings = Settings()
