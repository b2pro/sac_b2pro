from uuid import UUID, uuid4

import pytest

from sac.application.use_cases.preferences import (
    GetUserPreferencesUseCase,
    UpdateUserPreferencesUseCase,
)
from sac.domain.entities import UserPreferences
from sac.domain.errors import ValidationError


class InMemoryUserPreferencesRepository:
    def __init__(self) -> None:
        self.store: dict[UUID, UserPreferences] = {}

    async def get(self, user_id: UUID) -> UserPreferences | None:
        return self.store.get(user_id)

    async def upsert(self, prefs: UserPreferences) -> None:
        self.store[prefs.user_id] = prefs


async def test_get_devolve_defaults_quando_repo_nao_tem_linha() -> None:
    # sem linha gravada, o use case nao pode criar nada no repo -- so devolve
    # os defaults do dataclass. store continuar vazio prova que nao houve
    # upsert disfarcado de leitura.
    repo = InMemoryUserPreferencesRepository()
    user_id = uuid4()

    prefs = await GetUserPreferencesUseCase(repo).execute(user_id)

    assert prefs == UserPreferences(user_id=user_id)
    assert prefs.theme == "sistema"
    assert prefs.notify_toast is True
    assert prefs.notify_sound is False
    assert repo.store == {}


async def test_get_devolve_o_que_esta_gravado() -> None:
    repo = InMemoryUserPreferencesRepository()
    user_id = uuid4()
    gravado = UserPreferences(
        user_id=user_id, theme="escuro", notify_toast=False, notify_sound=True
    )
    await repo.upsert(gravado)

    prefs = await GetUserPreferencesUseCase(repo).execute(user_id)

    assert prefs == gravado


async def test_update_grava_e_devolve_preferencias() -> None:
    repo = InMemoryUserPreferencesRepository()
    user_id = uuid4()

    prefs = await UpdateUserPreferencesUseCase(repo).execute(
        user_id, theme="escuro", notify_toast=False, notify_sound=True
    )

    assert prefs == UserPreferences(
        user_id=user_id, theme="escuro", notify_toast=False, notify_sound=True
    )
    assert repo.store[user_id] == prefs


async def test_update_rejeita_tema_invalido() -> None:
    # theme so vem validado pelo Literal do Pydantic no HTTP; quem chama o use
    # case direto (fora do FastAPI) precisa do mesmo contrato de erro do
    # dominio, entao o use case valida de novo.
    repo = InMemoryUserPreferencesRepository()
    user_id = uuid4()

    with pytest.raises(ValidationError):
        await UpdateUserPreferencesUseCase(repo).execute(
            user_id, theme="roxo", notify_toast=True, notify_sound=False
        )

    assert repo.store == {}
