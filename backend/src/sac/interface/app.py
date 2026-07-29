from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.settings import Settings
from sac.infrastructure.storage import build_storage
from sac.interface.errors import register_error_handlers
from sac.interface.rate_limit import SlidingWindowRateLimiter
from sac.interface.routers import (
    auth,
    cadastros_catalog,
    cadastros_customers,
    cadastros_products,
    cep,
    health,
    members,
    platform_tenants,
    platform_users,
    tickets,
)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await app.state.engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="SAC-B2PRO", lifespan=_lifespan)
    app.state.settings = settings
    app.state.engine = build_engine(settings.database_url)
    app.state.session_factory = build_session_factory(app.state.engine)
    app.state.storage = build_storage(settings)
    app.state.login_limiter = SlidingWindowRateLimiter()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(auth.router, prefix="/api")
    app.include_router(platform_tenants.router, prefix="/api")
    app.include_router(platform_users.router, prefix="/api")
    app.include_router(cadastros_catalog.marcas_router, prefix="/api")
    app.include_router(cadastros_catalog.defeitos_router, prefix="/api")
    app.include_router(cadastros_catalog.solucoes_router, prefix="/api")
    app.include_router(cadastros_catalog.canais_router, prefix="/api")
    app.include_router(cadastros_customers.router, prefix="/api")
    app.include_router(cadastros_products.router, prefix="/api")
    app.include_router(cep.router, prefix="/api")
    app.include_router(tickets.router, prefix="/api")
    app.include_router(members.router, prefix="/api")
    return app
