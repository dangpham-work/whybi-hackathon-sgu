"""Định dạng lỗi thống nhất theo mục 5.4.1 của đề cương:

{ "error": { "code": "NODE_LOCKED", "message": "…", "details": {…} } }
"""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    """Lỗi nghiệp vụ. Ví dụ: raise AppError(409, "CYCLE_DETECTED", "…", {"path": [...]})"""

    def __init__(self, status: int, code: str, message: str = "", details: dict[str, Any] | None = None):
        super().__init__(message or code)
        self.status = status
        self.code = code
        self.message = message or code
        self.details = details or {}


class NotImplementedYet(AppError):
    """Endpoint đã khai báo theo Bảng 5.10 nhưng thẻ việc chưa làm. Trả 501 kèm mã thẻ."""

    def __init__(self, card: str):
        super().__init__(501, "NOT_IMPLEMENTED", f"Chưa cài đặt – xem thẻ {card}", {"card": card})


def _body(code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content=_body(exc.code, exc.message, exc.details))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND"}.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=_body(code, str(exc.detail)))

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content=_body("VALIDATION_ERROR", "Dữ liệu không hợp lệ", {"errors": exc.errors()}),
        )
