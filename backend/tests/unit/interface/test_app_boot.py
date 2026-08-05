import pytest

from sac.infrastructure.settings import Settings
from sac.interface.app import create_app


def test_create_app_recusa_subir_em_producao_sem_segredo_proprio() -> None:
    """A guarda tem de ser a primeira coisa do create_app: uma aplicacao que sobe
    assinando token com o segredo de desenvolvimento e pior do que uma que nao
    sobe."""
    with pytest.raises(RuntimeError):
        create_app(Settings(jwt_secret=""))
