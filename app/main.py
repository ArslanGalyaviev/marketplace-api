import json
import logging
import time
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.generated.routes import router

logger = logging.getLogger("api_logger")
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter("%(message)s"))
logger.addHandler(handler)

SENSITIVE_KEYS = {"password", "token", "refresh_token", "access_token", "secret"}


def mask_sensitive_data(data):
    if isinstance(data, dict):
        return {
            k: ("***" if k.lower() in SENSITIVE_KEYS else mask_sensitive_data(v))
            for k, v in data.items()
        }
    elif isinstance(data, list):
        return [mask_sensitive_data(item) for item in data]
    return data


app = FastAPI(title="Simple Marketplace", version="1.0.0")


def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title, version=app.version, routes=app.routes
    )
    for path in openapi_schema["paths"].values():
        for method in path.values():
            if "responses" in method and "422" in method["responses"]:
                del method["responses"]["422"]
    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    body = None
    response = None

    try:
        if request.method in ("POST", "PUT", "DELETE"):
            body_bytes = await request.body()
            if body_bytes:
                try:
                    parsed = json.loads(body_bytes)
                    body = json.dumps(mask_sensitive_data(parsed), ensure_ascii=False)
                except Exception:
                    body = "*** unparsed body ***"

        response = await call_next(request)

    except Exception as exc:
        logger.error(
            json.dumps(
                {
                    "event": "unhandled_exception",
                    "request_id": request_id,
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
        )
        response = JSONResponse(
            status_code=500,
            content={
                "error_code": "INTERNAL_SERVER_ERROR",
                "message": "Внутренняя ошибка сервера",
            },
        )
    finally:
        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
        log_data = {
            "request_id": request_id,
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": response.status_code if response else 500,
            "duration_ms": duration_ms,
            "user_id": None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        if body:
            log_data["request_body"] = body

        logger.info(json.dumps(log_data, ensure_ascii=False))
        if response:
            response.headers["X-Request-Id"] = request_id
        return response


app.include_router(router)


@app.exception_handler(RequestValidationError)
def validation_error(request, exc):
    problems = []
    for error in exc.errors():
        problems.append(
            {"field": ".".join(str(x) for x in error["loc"]), "message": error["msg"]}
        )
    return JSONResponse(
        status_code=400,
        content={
            "error_code": "VALIDATION_ERROR",
            "message": "Некорректные данные",
            "details": {"fields": problems},
        },
    )


@app.exception_handler(HTTPException)
def http_error(request, exc):
    if isinstance(exc.detail, dict) and "error_code" in exc.detail:
        return JSONResponse(status_code=exc.status_code, content=exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error_code": "VALIDATION_ERROR", "message": str(exc.detail)},
    )
