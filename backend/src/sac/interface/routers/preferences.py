from fastapi import APIRouter, Depends

from sac.application.ports import TokenPayload
from sac.application.use_cases.preferences import (
    GetUserPreferencesUseCase,
    UpdateUserPreferencesUseCase,
)
from sac.infrastructure.repositories import SqlUserPreferencesRepository
from sac.interface.deps import get_current_identity, get_user_preferences_repository
from sac.interface.schemas import PreferencesIn, PreferencesOut, preferences_out

router = APIRouter(prefix="/preferencias", tags=["preferencias"])


@router.get("", response_model=PreferencesOut)
async def get_preferences(
    identity: TokenPayload = Depends(get_current_identity),
    repo: SqlUserPreferencesRepository = Depends(get_user_preferences_repository),
) -> PreferencesOut:
    prefs = await GetUserPreferencesUseCase(repo).execute(identity.user_id)
    return preferences_out(prefs)


@router.put("", response_model=PreferencesOut)
async def update_preferences(
    body: PreferencesIn,
    identity: TokenPayload = Depends(get_current_identity),
    repo: SqlUserPreferencesRepository = Depends(get_user_preferences_repository),
) -> PreferencesOut:
    # user_id vem sempre do token (identity), nunca do corpo: ninguem le nem
    # grava a preferencia de outro usuario so por conhecer o id dele.
    prefs = await UpdateUserPreferencesUseCase(repo).execute(
        identity.user_id, body.theme, body.notify_toast, body.notify_sound
    )
    return preferences_out(prefs)
