from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from sac.infrastructure.repositories import SqlUserRepository
from sac.infrastructure.seed import seed_super_admin
from sac.infrastructure.settings import Settings


async def test_seed_cria_super_admin_uma_unica_vez(
    engine: AsyncEngine, session: AsyncSession, database: str
) -> None:
    settings = Settings(
        database_url=database,
        seed_admin_email="root@b2pro.com",
        seed_admin_password="senha-forte-123",
    )

    primeira = await seed_super_admin(settings)
    segunda = await seed_super_admin(settings)

    assert "criado" in primeira
    assert "ja existe" in segunda

    user = await SqlUserRepository(session).get_by_email("root@b2pro.com")
    assert user is not None and user.is_super_admin


async def test_seed_sem_credenciais_orienta_configuracao(database: str) -> None:
    settings = Settings(database_url=database, seed_admin_email="", seed_admin_password="")
    resultado = await seed_super_admin(settings)
    assert "SAC_SEED_ADMIN_EMAIL" in resultado
