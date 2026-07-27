from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sac.infrastructure.db import build_engine, build_session_factory
from sac.infrastructure.settings import Settings
from sac.interface.errors import register_error_handlers
from sac.interface.rate_limit import SlidingWindowRateLimiter
from sac.interface.routers import auth, health, platform_tenants, platform_users


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
    return app
