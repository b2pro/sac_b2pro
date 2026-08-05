import pytest

from sac.infrastructure.settings import (
    DEV_JWT_SECRET,
    MIN_JWT_SECRET_LENGTH,
    Settings,
    ensure_boot_secrets,
)

SEGREDO_FORTE = "x" * MIN_JWT_SECRET_LENGTH


def test_ambiente_default_e_producao() -> None:
    """Fail-safe: esquecer a variavel derruba o boot em vez de fazer a aplicacao
    assinar token com segredo do repositorio. O desenvolvimento e que precisa
    dizer que e desenvolvimento."""
    assert Settings(jwt_secret=SEGREDO_FORTE).environment == "production"


def test_producao_sem_segredo_aborta_o_boot() -> None:
    with pytest.raises(RuntimeError) as exc:
        ensure_boot_secrets(Settings(jwt_secret=""))

    assert "SAC_JWT_SECRET" in str(exc.value)


def test_producao_com_o_segredo_de_desenvolvimento_aborta_o_boot() -> None:
    """O default antigo era uma string fixa versionada no repositorio: quem lesse
    o codigo forjava um token com `sa: true` e virava super_admin. Mesmo que
    alguem reponha esse valor por env, producao recusa."""
    with pytest.raises(RuntimeError):
        ensure_boot_secrets(Settings(jwt_secret=DEV_JWT_SECRET))


def test_producao_com_segredo_curto_aborta_o_boot() -> None:
    with pytest.raises(RuntimeError):
        ensure_boot_secrets(Settings(jwt_secret="x" * (MIN_JWT_SECRET_LENGTH - 1)))


def test_producao_com_segredo_forte_passa() -> None:
    ensure_boot_secrets(Settings(jwt_secret=SEGREDO_FORTE))


def test_desenvolvimento_sem_segredo_usa_o_fallback_e_nao_aborta() -> None:
    settings = Settings(environment="development", jwt_secret="")

    ensure_boot_secrets(settings)

    assert settings.jwt_secret == DEV_JWT_SECRET


def test_desenvolvimento_respeita_segredo_proprio_quando_informado() -> None:
    settings = Settings(environment="development", jwt_secret=SEGREDO_FORTE)

    assert settings.jwt_secret == SEGREDO_FORTE
