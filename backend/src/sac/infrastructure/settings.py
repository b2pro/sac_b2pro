from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Segredo usado APENAS quando SAC_ENVIRONMENT=development. Nao e um default: em
# qualquer outro ambiente, `ensure_boot_secrets` recusa este valor.
DEV_JWT_SECRET = "dev-secret-nao-serve-em-producao"
MIN_JWT_SECRET_LENGTH = 32
DEVELOPMENT = "development"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SAC_", env_file=".env", extra="ignore")

    # Default fail-safe: quem nao diz nada e tratado como producao. Se um deploy
    # esquecer a variavel, o boot para (ver ensure_boot_secrets) em vez de a
    # aplicacao subir assinando token com segredo conhecido. O caminho errado tem
    # de ser o barulhento.
    environment: str = "production"
    database_url: str = "postgresql+asyncpg://sac:sac@localhost:5432/sac"
    jwt_secret: str = ""
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
    # Margem de idade da reconciliacao de orfaos: objeto mais novo que isso
    # nunca e apagado, porque pode ser um upload em voo (objeto no bucket, linha
    # ainda nao gravada - a foto de produto nao tem linha nenhuma antes do
    # confirmar). O floor ge=1 e a guarda de verdade: zerar isso por env ou por
    # override de compose destruiria todo upload em andamento na proxima
    # passada, sem volta, e comentario nao segura operacao irreversivel.
    reconcile_orphans_hours: int = Field(default=24, ge=1)
    attachment_max_bytes: int = 52_428_800
    attachment_max_per_ticket: int = 10
    trusted_proxy: bool = False
    login_rate_ip_tenant: int = 5
    login_rate_ip: int = 30
    login_rate_window_seconds: float = 60.0

    @property
    def is_development(self) -> bool:
        return self.environment.strip().lower() == DEVELOPMENT

    @model_validator(mode="after")
    def _fallback_de_desenvolvimento(self) -> "Settings":
        """Em desenvolvimento, `docker compose up` e `dev.ps1` tem de funcionar sem
        ninguem gerar segredo a mao. Fora dele, o campo fica vazio de proposito -
        e vazio nao assina token nenhum, porque o boot para antes."""
        if self.is_development and not self.jwt_secret:
            self.jwt_secret = DEV_JWT_SECRET
        return self


def ensure_boot_secrets(settings: Settings) -> None:
    """Aborta o boot quando o deploy nao trouxe segredo proprio.

    O risco que isso fecha: uma aplicacao que sobe normalmente com um segredo
    conhecido assina tokens forjaveis. Quem tem o segredo emite um access token
    com `sa: true` e vira super_admin, porque `require_super_admin` confia no
    claim. Falhar no boot e a unica resposta segura.
    """
    if settings.is_development:
        return
    if not settings.jwt_secret:
        raise RuntimeError(
            "SAC_JWT_SECRET nao definido. Gere um segredo proprio "
            f"(minimo {MIN_JWT_SECRET_LENGTH} caracteres) ou rode com "
            f"SAC_ENVIRONMENT={DEVELOPMENT}."
        )
    if settings.jwt_secret == DEV_JWT_SECRET:
        raise RuntimeError(
            "SAC_JWT_SECRET esta com o segredo de desenvolvimento, que e publico "
            "no repositorio. Gere um segredo proprio para este ambiente."
        )
    if len(settings.jwt_secret) < MIN_JWT_SECRET_LENGTH:
        raise RuntimeError(
            f"SAC_JWT_SECRET tem menos de {MIN_JWT_SECRET_LENGTH} caracteres: "
            "curto demais para assinar HS256."
        )
