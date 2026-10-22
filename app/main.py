import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.routes_runs import router as runs_router
from app.api.routes_workflows import router as workflows_router
from app.config import LOG_LEVEL
from app.errors import AppError

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("app")

app = FastAPI(title="Visual Workflow Runner")
app.include_router(workflows_router)
app.include_router(runs_router)


def error_response(status_code: int, code: str, message: str, details: list | None = None):
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or []}},
    )


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(part) for part in err["loc"]), "message": err["msg"]}
        for err in exc.errors()
    ]
    return error_response(
        422, "INVALID_REQUEST", "The request body or parameters are invalid.", details
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(request: Request, exc: StarletteHTTPException):
    codes = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}
    code = codes.get(exc.status_code, "HTTP_ERROR")
    return error_response(exc.status_code, code, str(exc.detail))


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    # The full details go to the server log, never to the user.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")


@app.get("/healthz")
def healthz():
    return {"status": "ok"}