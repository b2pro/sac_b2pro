from uuid import UUID

from fastapi import APIRouter, Depends

from sac.application.use_cases.platform_users import (
    CreateUserInput,
    CreateUserUseCase,
    ListUsersUseCase,
    ResetPasswordUseCase,
    SetUserActiveUseCase,
)
from sac.interface.deps import (
    get_create_user_use_case,
    get_list_users_use_case,
    get_reset_password_use_case,
    get_set_user_active_use_case,
    require_super_admin,
)
from sac.interface.schemas import PasswordResetIn, UserActiveIn, UserCreateIn, UserOut

router = APIRouter(
    prefix="/platform/users",
    tags=["platform"],
    dependencies=[Depends(require_super_admin)],
)


def _user_out(user: object) -> UserOut:
    return UserOut.model_validate(user, from_attributes=True)


@router.post("", response_model=UserOut, status_code=201)
async def create_user(
    body: UserCreateIn,
    use_case: CreateUserUseCase = Depends(get_create_user_use_case),
) -> UserOut:
    user = await use_case.execute(
        CreateUserInput(
            name=body.name,
            email=body.email,
            password=body.password,
            is_super_admin=body.is_super_admin,
        )
    )
    return _user_out(user)


@router.get("", response_model=list[UserOut])
async def list_users(
    use_case: ListUsersUseCase = Depends(get_list_users_use_case),
) -> list[UserOut]:
    return [_user_out(u) for u in await use_case.execute()]


@router.patch("/{user_id}/active", response_model=UserOut)
async def set_active(
    user_id: UUID,
    body: UserActiveIn,
    use_case: SetUserActiveUseCase = Depends(get_set_user_active_use_case),
) -> UserOut:
    return _user_out(await use_case.execute(user_id, body.active))


@router.post("/{user_id}/password", status_code=204)
async def reset_password(
    user_id: UUID,
    body: PasswordResetIn,
    use_case: ResetPasswordUseCase = Depends(get_reset_password_use_case),
) -> None:
    await use_case.execute(user_id, body.password)
