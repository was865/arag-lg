"""共通エラー応答 `{"error": {"code", "message"}}`（specs/003-ingestion/design.md §5）。"""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from arag.logging import get_logger

log = get_logger("arag.errors")

_DEFAULT_CODES = {
    400: ("bad_request", "要求の形式が正しくありません"),
    401: ("unauthenticated", "ログインが必要です"),
    403: ("forbidden", "この操作を行う権限がありません"),
    404: ("not_found", "見つかりません"),
    405: ("method_not_allowed", "この操作はできません"),
    409: ("conflict", "競合が発生しました"),
    413: ("payload_too_large", "ファイルが大きすぎます"),
    415: ("unsupported_media_type", "対応していない形式です"),
    422: ("invalid_request", "入力内容が正しくありません"),
}


class ApiError(Exception):
    """利用者に返すエラー。message は日本語。"""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message


def not_found(message: str = "見つかりません") -> ApiError:
    # 権限が無い場合も 404（存在を推測させない。R6）
    return ApiError(404, "not_found", message)


def error_body(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code, message = _DEFAULT_CODES.get(exc.status_code, ("error", "エラーが発生しました"))
        return JSONResponse(error_body(code, message), status_code=exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        code, message = _DEFAULT_CODES[422]
        return JSONResponse(error_body(code, message), status_code=422)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled_error", error_type=type(exc).__name__)
        body = error_body("internal_error", "サーバー内部でエラーが発生しました")
        return JSONResponse(body, status_code=500)
