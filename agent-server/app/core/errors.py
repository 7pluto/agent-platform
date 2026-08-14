from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse


@dataclass
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    details: Any = None


async def api_error_handler(_: Request, exc: ApiError) -> JSONResponse:
    body = {
        "code": exc.code,
        "message": exc.message,
        "request_id": None,
    }
    if exc.details is not None:
        body["details"] = exc.details
    return JSONResponse(status_code=exc.status_code, content=body)
