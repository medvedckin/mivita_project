from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_url: str = "postgresql://mivita:mivita_pass@localhost:5432/mivita_db"
    secret_key: str = "super-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60 * 12
    refresh_token_expire_days: int = 7
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    admin_username: str = "admin"
    admin_password: str = "admin"
    kitchen_username: str = "kitchen"
    kitchen_password: str = "kitchen"
    partner_username: str = "partner"
    partner_password: str = "partner"

    class Config:
        env_file = ".env"


settings = Settings()
