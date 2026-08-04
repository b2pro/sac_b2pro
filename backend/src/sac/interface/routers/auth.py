from fastapi import APIRouter, Depends, Request

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.infrastructure.settings import Settings
from sac.interface.deps import get_login_use_case, get_refresh_use_case
from sac.interface.rate_limit import SlidingWindowRateLimiter, client_ip
from sac.interface.schemas import LoginIn, LoginOut, RefreshIn, login_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
async def login(
    body: LoginIn,
    request: Request,
    use_case: LoginUseCase = Depends(get_login_use_case),
) -> LoginOut:
    settings: Settings = request.app.state.settings
    ip = client_ip(request, settings.trusted_proxy)
    ip_limiter: SlidingWindowRateLimiter = request.app.state.login_ip_limiter
    tenant_limiter: SlidingWindowRateLimiter = request.app.state.login_limiter
    ip_limiter.check(ip)
    tenant_limiter.check(f"{ip}:{body.tenant_slug or ''}")
    result = await use_case.execute(body.email, body.password, body.tenant_slug)
    return login_out(result)


@router.post("/refresh", response_model=LoginOut)
async def refresh(
    body: RefreshIn,
    request: Request,
    use_case: RefreshTokenUseCase = Depends(get_refresh_use_case),
) -> LoginOut:
    settings: Settings = request.app.state.settings
    ip = client_ip(request, settings.trusted_proxy)
    ip_limiter: SlidingWindowRateLimiter = request.app.state.login_ip_limiter
    ip_limiter.check(f"refresh:{ip}")
    result = await use_case.execute(body.refresh_token)
    return login_out(result)
