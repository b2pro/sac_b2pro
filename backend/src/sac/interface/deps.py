from collections.abc import AsyncIterator
from functools import lru_cache

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


@lru_cache
def get_hasher() -> Argon2PasswordHasher:
    return Argon2PasswordHasher()


def get_token_service(settings: Settings = Depends(get_settings)) -> JwtTokenService:
    return JwtTokenService.from_settings(settings)


def get_login_use_case(
    session: AsyncSession = Depends(get_session),
    hasher: Argon2PasswordHasher = Depends(get_hasher),
    tokens: JwtTokenService = Depends(get_token_service),
) -> LoginUseCase:
    return LoginUseCase(
        SqlUserRepository(session),
        SqlTenantRepository(session),
        SqlUserTenantRepository(session),
        hasher,
        tokens,
    )


def get_refresh_use_case(
    session: AsyncSession = Depends(get_session),
    tokens: JwtTokenService = Depends(get_token_service),
) -> RefreshTokenUseCase:
    return RefreshTokenUseCase(
        SqlUserRepository(session),
        SqlTenantRepository(session),
        SqlUserTenantRepository(session),
        tokens,
    )
