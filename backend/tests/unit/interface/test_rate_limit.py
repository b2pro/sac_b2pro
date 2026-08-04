import pytest
from starlette.requests import Request

from sac.interface.rate_limit import RateLimitedError, SlidingWindowRateLimiter, client_ip


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


def test_janela_larga_bloqueia_na_31a_tentativa_de_slugs_variados() -> None:
    now = 0.0
    limiter = SlidingWindowRateLimiter(max_attempts=30, window_seconds=60.0, clock=lambda: now)

    # a chave do limitador de IP nao inclui o slug: tentativas contra tenants
    # diferentes do mesmo IP consomem o mesmo orcamento.
    for _ in range(30):
        limiter.check("9.9.9.9")
    with pytest.raises(RateLimitedError):
        limiter.check("9.9.9.9")


def _make_request(*, client_host: str = "9.9.9.9", forwarded_for: str | None = None) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if forwarded_for is not None:
        headers.append((b"x-forwarded-for", forwarded_for.encode()))
    scope = {
        "type": "http",
        "headers": headers,
        "client": (client_host, 12345),
    }
    return Request(scope)


def test_client_ip_ignora_xff_sem_trusted_proxy() -> None:
    request = _make_request(client_host="9.9.9.9", forwarded_for="1.1.1.1")
    assert client_ip(request, trusted_proxy=False) == "9.9.9.9"


def test_client_ip_usa_primeiro_xff_com_trusted_proxy() -> None:
    request = _make_request(client_host="9.9.9.9", forwarded_for="1.1.1.1, 2.2.2.2")
    assert client_ip(request, trusted_proxy=True) == "1.1.1.1"


def test_client_ip_trusted_proxy_sem_xff_usa_client_host() -> None:
    request = _make_request(client_host="9.9.9.9")
    assert client_ip(request, trusted_proxy=True) == "9.9.9.9"
