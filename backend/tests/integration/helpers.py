from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from sac.domain.entities import Tenant, TenantStatus, User, UserTenant
from sac.domain.permissions import Role
from sac.infrastructure.models_tenant import (
    BrandModel,
    DefectTypeModel,
    PurchaseChannelModel,
    SolutionTypeModel,
)
from sac.infrastructure.provisioning import AlembicTenantProvisioner
from sac.infrastructure.repositories import (
    SqlTenantRepository,
    SqlUserRepository,
    SqlUserTenantRepository,
)
from sac.infrastructure.security import Argon2PasswordHasher, JwtTokenService
from sac.infrastructure.settings import Settings

HASHER = Argon2PasswordHasher()
DEFAULT_PASSWORD = "senha-forte-123"
_PASSWORD_HASH = HASHER.hash(DEFAULT_PASSWORD)


async def seed_user(
    session: AsyncSession,
    *,
    email: str,
    name: str = "Usuario Teste",
    is_super_admin: bool = False,
    active: bool = True,
) -> User:
    user = User(
        id=uuid4(),
        name=name,
        email=email,
        password_hash=_PASSWORD_HASH,
        is_super_admin=is_super_admin,
        active=active,
    )
    await SqlUserRepository(session).add(user)
    await session.commit()
    return user


async def seed_tenant(
    session: AsyncSession,
    *,
    slug: str,
    status: TenantStatus = TenantStatus.ATIVA,
    modules: dict[str, bool] | None = None,
) -> Tenant:
    tenant = Tenant(id=uuid4(), slug=slug, name=slug.upper(), status=status, modules=modules or {})
    await SqlTenantRepository(session).add(tenant)
    await session.commit()
    return tenant


async def seed_catalogo_minimo(engine: AsyncEngine, schema: str) -> None:
    """Uma entrada em cada catalogo, para o tenant conseguir abrir ticket.

    O provisionamento de producao nao semeia catalogo nenhum (ver
    sac.infrastructure.tenant_seeds): marca, defeito, solucao e canal descrevem a
    operacao de quem contratou. A maioria dos testes so precisa de "uma marca
    qualquer" e pega a primeira que encontra, entao o catalogo de teste nasce
    aqui. Quem depende de um nome especifico cadastra o seu -- estes nomes sao
    neutros de proposito, para nao colidir.
    """
    factory = async_sessionmaker(
        engine.execution_options(schema_translate_map={"tenant": schema}),
        expire_on_commit=False,
    )
    async with factory() as ts:
        ts.add_all(
            [
                BrandModel(id=uuid4(), name="Marca Teste"),
                DefectTypeModel(id=uuid4(), name="Defeito Teste"),
                SolutionTypeModel(id=uuid4(), name="Solucao Teste"),
                PurchaseChannelModel(id=uuid4(), name="Canal Teste"),
            ]
        )
        await ts.commit()


async def seed_provisioned_tenant(
    session: AsyncSession, engine: AsyncEngine, *, slug: str, catalogo: bool = True
) -> Tenant:
    tenant = await seed_tenant(session, slug=slug)
    await AlembicTenantProvisioner(engine).provision(tenant.schema_name)
    if catalogo:
        await seed_catalogo_minimo(engine, tenant.schema_name)
    return tenant


async def seed_link(
    session: AsyncSession,
    *,
    user: User,
    tenant: Tenant,
    role: Role = Role.ADMIN,
    active: bool = True,
) -> UserTenant:
    link = UserTenant(user_id=user.id, tenant_id=tenant.id, role=role, active=active)
    await SqlUserTenantRepository(session).add(link)
    await session.commit()
    return link


def token_for(
    user: User, *, tenant_slug: str | None = None, role: Role | None = None
) -> dict[str, str]:
    tokens = JwtTokenService.from_settings(Settings())
    access = tokens.create_access(
        user.id, tenant_slug, role, user.is_super_admin, user.credentials_version
    )
    return {"Authorization": f"Bearer {access}"}
