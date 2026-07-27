import asyncio

from sac.application.use_cases.platform_users import CreateUserInput, CreateUserUseCase
from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.repositories import SqlUserRepository
from sac.infrastructure.security import Argon2PasswordHasher
from sac.infrastructure.settings import Settings


async def seed_super_admin(settings: Settings) -> str:
    if not settings.seed_admin_email or not settings.seed_admin_password:
        return "configure SAC_SEED_ADMIN_EMAIL e SAC_SEED_ADMIN_PASSWORD no .env"
    engine = build_engine(settings.database_url)
    try:
        factory = build_session_factory(engine)
        async with factory() as session:
            users = SqlUserRepository(session)
            email = settings.seed_admin_email.strip().lower()
            if await users.get_by_email(email) is not None:
                return f"super admin ja existe: {email}"
            await CreateUserUseCase(users, Argon2PasswordHasher()).execute(
                CreateUserInput(
                    name=settings.seed_admin_name,
                    email=email,
                    password=settings.seed_admin_password,
                    is_super_admin=True,
                )
            )
            await session.commit()
            return f"super admin criado: {email}"
    finally:
        await engine.dispose()


def main() -> None:
    print(asyncio.run(seed_super_admin(Settings())))


if __name__ == "__main__":
    main()
