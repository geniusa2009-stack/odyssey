"""Structured error responses (one envelope, never stack traces) for every FastAPI app.

Shared by the v1 application (``app/main.py``) and the mounted ``odyssey.game.v1`` sub-app
(``app/game/api/app.py``), so both speak exactly the same public error contract
(``app/core/errors.py``, docs/API_CONTRACT.md#errors).
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.errors import AppError, app_error_body, error_body
from app.core.logging import request_id_var

log = logging.getLogger("odyssey")


def _rid(request: Request) -> str | None:
    return request_id_var.get()


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError) -> JSONResponse:
        if exc.status_code >= 500:
            log.error("app_error", extra={"error_code": exc.code})
        return JSONResponse(app_error_body(exc, _rid(request)), status_code=exc.status_code)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {"loc": [str(p) for p in e.get("loc", ())], "msg": e.get("msg"), "type": e.get("type")}
            for e in exc.errors()
        ][:50]
        return JSONResponse(
            error_body(
                "VALIDATION_ERROR",
                "request validation failed",
                _rid(request),
                {"errors": errors},
                reason="validation_error",
            ),
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}.get(exc.status_code, "INVALID_REQUEST")
        return JSONResponse(
            error_body(code, str(exc.detail), _rid(request), reason=code.lower()),
            status_code=exc.status_code,
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", extra={"error_code": "internal_error"})
        return JSONResponse(
            error_body("INTERNAL_ERROR", "an internal error occurred", _rid(request)),
            status_code=500,
        )
