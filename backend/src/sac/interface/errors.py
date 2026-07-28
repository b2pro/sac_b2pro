from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from sac.domain.errors import DomainError

STATUS_BY_CODE = {
    "validation_error": 422,
    "not_found": 404,
    "conflict": 409,
    "permission_denied": 403,
    "auth_error": 401,
    "rate_limited": 429,
    "cep_indisponivel": 503,
    "transicao_invalida": 409,
}


async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
    return JSONResponse(
        status_code=STATUS_BY_CODE.get(exc.code, 400),
        content={"code": exc.code, "message": str(exc), "details": exc.details},
    )


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "validation_error",
            "message": "dados invalidos",
            "details": {"errors": jsonable_encoder(exc.errors())},
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(DomainError, domain_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(
        RequestValidationError,
        request_validation_error_handler,  # type: ignore[arg-type]
    )
