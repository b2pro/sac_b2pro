from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class ObjectHead:
    content_type: str
    size_bytes: int


class StoragePort(Protocol):
    def presigned_put(
        self, key: str, content_type: str, max_bytes: int, ttl_seconds: int
    ) -> str: ...
    def presigned_get(self, key: str, ttl_seconds: int) -> str: ...
    def head(self, key: str) -> ObjectHead | None: ...
    def put_bytes(self, key: str, data: bytes, content_type: str) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
