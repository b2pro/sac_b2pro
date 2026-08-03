from uuid import UUID

from sac.application.ports import UserPreferencesRepository
from sac.domain.entities import UserPreferences
from sac.domain.errors import ValidationError

VALID_THEMES = {"claro", "escuro", "sistema"}


class GetUserPreferencesUseCase:
    def __init__(self, preferences: UserPreferencesRepository) -> None:
        self._preferences = preferences

    async def execute(self, user_id: UUID) -> UserPreferences:
        # sem linha gravada, devolve os defaults do dataclass sem escrever
        # nada: GET nao pode ser uma escrita disfarcada.
        prefs = await self._preferences.get(user_id)
        return prefs if prefs is not None else UserPreferences(user_id=user_id)


class UpdateUserPreferencesUseCase:
    def __init__(self, preferences: UserPreferencesRepository) -> None:
        self._preferences = preferences

    async def execute(
        self, user_id: UUID, theme: str, notify_toast: bool, notify_sound: bool
    ) -> UserPreferences:
        # o schema Pydantic (Literal) ja barra tema invalido no HTTP com 422,
        # mas quem chama este use case fora do FastAPI (script, outro use
        # case) nao passa por ali -- precisa do mesmo contrato de erro do
        # dominio, entao valida de novo aqui.
        if theme not in VALID_THEMES:
            raise ValidationError("tema invalido", details={"field": "theme", "value": theme})
        prefs = UserPreferences(
            user_id=user_id, theme=theme, notify_toast=notify_toast, notify_sound=notify_sound
        )
        await self._preferences.upsert(prefs)
        return prefs
