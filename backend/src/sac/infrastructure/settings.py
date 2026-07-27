from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAC_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://sac:sac@localhost:5432/sac"
    jwt_secret: str = "dev-secret-troque-em-producao"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 7
    cors_origins: list[str] = ["http://localhost:5173"]
    seed_admin_name: str = "Administrador"
    seed_admin_email: str = ""
    seed_admin_password: str = ""
