import time
from collections import deque
from collections.abc import Callable

from sac.domain.errors import DomainError


class RateLimitedError(DomainError):
    code = "rate_limited"


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
