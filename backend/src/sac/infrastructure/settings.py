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
    s3_endpoint_url: str = "http://localhost:9000"
    s3_public_endpoint_url: str = ""
    s3_region: str = "us-east-1"
    s3_bucket: str = "sac-dev"
    s3_access_key: str = "sacminio"
    s3_secret_key: str = "sacminio123"
    presigned_ttl_seconds: int = 300
    pending_expiration_minutes: int = 30
    attachment_max_bytes: int = 52_428_800
    attachment_max_per_ticket: int = 10
