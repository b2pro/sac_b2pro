from fastapi import APIRouter, Depends, Request

from sac.application.use_cases.auth import LoginUseCase, RefreshTokenUseCase
from sac.interface.deps import get_login_use_case, get_refresh_use_case
from sac.interface.rate_limit import SlidingWindowRateLimiter
from sac.interface.schemas import LoginIn, LoginOut, RefreshIn, login_out

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
async def login(
    body: LoginIn,
    request: Request,
    use_case: LoginUseCase = Depends(get_login_use_case),
) -> LoginOut:
    limiter: SlidingWindowRateLimiter = request.app.state.login_limiter
    client_ip = request.client.host if request.client else "desconhecido"
    limiter.check(f"{client_ip}:{body.tenant_slug or ''}")
    result = await use_case.execute(body.email, body.password, body.tenant_slug)
    return login_out(result)


@router.post("/refresh", response_model=LoginOut)
async def refresh(
    body: RefreshIn,
    use_case: RefreshTokenUseCase = Depends(get_refresh_use_case),
) -> LoginOut:
    result = await use_case.execute(body.refresh_token)
    return login_out(result)
