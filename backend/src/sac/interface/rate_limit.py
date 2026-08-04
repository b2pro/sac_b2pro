"""Rate limiting da autenticacao.

Implementacao em memoria por decisao do spec: o deploy e instancia unica,
sem Redis nem outro store compartilhado nesta fase. O estado (contadores por
chave) vive no processo e se perde a cada reinicio, o que e aceitavel para o
proposito (conter forca bruta, nao persistir historico). Se um dia houver
mais de uma instancia atras de um load balancer, trocar por um backend
compartilhado exige apenas outra implementacao do mesmo `check(key)` --
routers e `app.py` nao precisam mudar.
"""

import time
from collections import deque
from collections.abc import Callable

from fastapi import Request

from sac.domain.errors import DomainError


class RateLimitedError(DomainError):
    code = "rate_limited"


def client_ip(request: Request, trusted_proxy: bool) -> str:
    """Resolve o IP do cliente.

    Com `trusted_proxy=True`, confia no primeiro IP de `X-Forwarded-For`
    (o mais proximo do cliente original) quando o header estiver presente.
    Sem a flag -- ou sem o header --, usa o IP da conexao TCP direta. A flag
    e um opt-in explicito: sem um proxy reverso configurado para higienizar
    o header, confiar em XFF por padrao permite falsificar o IP e escapar
    do limitador.
    """
    if trusted_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconhecido"


class SlidingWindowRateLimiter:
    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}

    def check(self, key: str) -> None:
        now = self._clock()
        hits = self._hits.setdefault(key, deque())
        while hits and now - hits[0] > self._window:
            hits.popleft()
        if len(hits) >= self._max:
            raise RateLimitedError("muitas tentativas, aguarde um instante")
        hits.append(now)
