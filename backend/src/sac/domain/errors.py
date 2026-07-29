class DomainError(Exception):
    code: str = "domain_error"

    def __init__(self, message: str, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.details: dict[str, object] = details or {}


class ValidationError(DomainError):
    code = "validation_error"


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    code = "conflict"


class PermissionDeniedError(DomainError):
    code = "permission_denied"


class AuthError(DomainError):
    code = "auth_error"


class CepUnavailableError(DomainError):
    code = "cep_indisponivel"


class InvalidTransitionError(DomainError):
    code = "transicao_invalida"


class StorageUnavailableError(DomainError):
    code = "storage_indisponivel"
