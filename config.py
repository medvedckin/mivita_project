from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://mivita:mivita_pass@localhost:5432/mivita_db"
    secret_key: str = "super-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    class Config:
        env_file = ".env"


settings = Settings()
