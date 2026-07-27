import pytest

from sac.interface.rate_limit import RateLimitedError, SlidingWindowRateLimiter


def test_bloqueia_apos_o_limite_e_libera_depois_da_janela() -> None:
    now = 0.0
    limiter = SlidingWindowRateLimiter(max_attempts=3, window_seconds=60.0, clock=lambda: now)

    for _ in range(3):
        limiter.check("1.2.3.4:b2pro")
    with pytest.raises(RateLimitedError):
        limiter.check("1.2.3.4:b2pro")

    limiter.check("5.6.7.8:b2pro")  # outra chave nao e afetada

    now = 61.0
    limiter.check("1.2.3.4:b2pro")  # janela expirou
