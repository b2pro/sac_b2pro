from dataclasses import dataclass
from uuid import UUID, uuid4

from sac.application.ports import (
    PasswordHasherPort,
    TenantRepository,
    UserRepository,
    UserTenantRepository,
)
from sac.domain.entities import User, UserTenant
from sac.domain.errors import ConflictError, NotFoundError, ValidationError
from sac.domain.permissions import Role

MIN_PASSWORD_LENGTH = 8


def validate_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValidationError(f"senha deve ter ao menos {MIN_PASSWORD_LENGTH} caracteres")


@dataclass(frozen=True)
class CreateUserInput:
    name: str
    email: str
    password: str
    is_super_admin: bool = False


class CreateUserUseCase:
    def __init__(self, users: UserRepository, hasher: PasswordHasherPort) -> None:
        self._users = users
        self._hasher = hasher

    async def execute(self, data: CreateUserInput) -> User:
        validate_password(data.password)
        email = data.email.strip().lower()
        if await self._users.get_by_email(email) is not None:
            raise ConflictError("email ja cadastrado")
        user = User(
            id=uuid4(),
            name=data.name,
            email=email,
            password_hash=self._hasher.hash(data.password),
            is_super_admin=data.is_super_admin,
        )
        await self._users.add(user)
        return user


class ListUsersUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self) -> list[User]:
        return await self._users.list_all()


class SetUserActiveUseCase:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def execute(self, user_id: UUID, active: bool) -> User:
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("usuario nao encontrado")
        user.active = active
        await self._users.update(user)
        return user


class ResetPasswordUseCase:
    def __init__(self, users: UserRepository, hasher: PasswordHasherPort) -> None:
        self._users = users
        self._hasher = hasher

    async def execute(self, user_id: UUID, new_password: str) -> None:
        validate_password(new_password)
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise NotFoundError("usuario nao encontrado")
        user.password_hash = self._hasher.hash(new_password)
        await self._users.update(user)


class LinkUserToTenantUseCase:
    def __init__(
        self,
        users: UserRepository,
        tenants: TenantRepository,
        links: UserTenantRepository,
    ) -> None:
        self._users = users
        self._tenants = tenants
        self._links = links

    async def execute(self, user_id: UUID, tenant_id: UUID, role: Role) -> UserTenant:
        if await self._users.get_by_id(user_id) is None:
            raise NotFoundError("usuario nao encontrado")
        if await self._tenants.get_by_id(tenant_id) is None:
            raise NotFoundError("tenant nao encontrado")
        link = UserTenant(user_id=user_id, tenant_id=tenant_id, role=role)
        await self._links.add(link)
        return link


class UnlinkUserFromTenantUseCase:
    def __init__(self, links: UserTenantRepository) -> None:
        self._links = links

    async def execute(self, user_id: UUID, tenant_id: UUID) -> None:
        await self._links.remove(user_id, tenant_id)


class ListTenantLinksUseCase:
    def __init__(self, links: UserTenantRepository) -> None:
        self._links = links

    async def execute(self, tenant_id: UUID) -> list[UserTenant]:
        return await self._links.list_for_tenant(tenant_id)
