"""Unified API error format."""
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any


class APIError(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None


class NexsysError(Exception):
    def __init__(self, message: str, code: str = "INTERNAL", status: int = 500):
        self.message = message
        self.code = code
        self.status = status
        super().__init__(message)


class NotFoundError(NexsysError):
    def __init__(self, resource: str, id: str):
        super().__init__(f"{resource} '{id}' not found", code="NOT_FOUND", status=404)


class ConflictError(NexsysError):
    def __init__(self, message: str):
        super().__init__(message, code="CONFLICT", status=409)


class ValidationError(NexsysError):
    def __init__(self, message: str):
        super().__init__(message, code="VALIDATION", status=422)


async def nexsys_error_handler(request: Request, exc: NexsysError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status,
        content={"error": exc.message, "detail": None, "code": exc.code},
    )


def _cors_headers(request: Request) -> dict[str, str]:
    """Заголовки CORS для ответа об ошибке.

    Обработчик Exception живёт в самом внешнем слое Starlette — выше
    CORSMiddleware, поэтому его ответы уходили без этих заголовков.
    Браузер такой ответ не показывал вовсе, и фронтенд видел «нет связи»
    вместо настоящей причины сбоя.
    """
    from .config import CORS_ORIGINS

    origin = request.headers.get("origin")
    if origin and origin in CORS_ORIGINS:
        return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"}
    return {}


async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": str(exc), "detail": None, "code": "INTERNAL"},
        headers=_cors_headers(request),
    )
