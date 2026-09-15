from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.projects import router as projects_router
from app.api.documents import router as documents_router
from app.api.rules import router as rules_router
from app.api.generation import router as generation_router
from app.api.review import router as review_router
from app.api.quality import router as quality_router
from app.api.interview import router as interview_router
from app.config import get_settings
from app.schemas import HealthRead

settings = get_settings()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    if settings.agent_env != "test":
        if settings.use_mocks:
            raise RuntimeError("USE_MOCKS is forbidden outside the automated test environment")
        if settings.llm_provider != "openai_compatible":
            raise RuntimeError("LLM_PROVIDER must be openai_compatible")
        if not settings.llm_generator_model.strip():
            raise RuntimeError("LLM_GENERATOR_MODEL must be configured")
        secret_path = Path(settings.llm_api_key_file)
        if not secret_path.is_file() or not secret_path.read_text(encoding="utf-8").strip():
            raise RuntimeError("The LLM API key secret must be configured")
    yield


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.middleware("http")
async def limit_request_body(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            content_type = request.headers.get("content-type", "")
            allowed_size = (
                settings.max_request_body_bytes
                if content_type.startswith("multipart/form-data")
                else settings.max_json_request_body_bytes
            )
            if int(content_length) > allowed_size:
                return problem(request, 413, "Payload too large", "Request body exceeds the allowed size.")
        except ValueError:
            return problem(request, 400, "Invalid request", "Content-Length header is invalid.")
    return await call_next(request)


def problem(request: Request, status_code: int, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
            "instance": request.url.path,
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    return problem(request, exc.status_code, "Request failed", str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, _exc: RequestValidationError) -> JSONResponse:
    return problem(request, 422, "Validation failed", "One or more fields are invalid.")


@app.get(f"{settings.api_prefix}/health", response_model=HealthRead, tags=["system"])
def health() -> HealthRead:
    return HealthRead(status="ok", environment=settings.agent_env, mocks_enabled=settings.use_mocks)


app.include_router(projects_router, prefix=settings.api_prefix)
app.include_router(documents_router, prefix=settings.api_prefix)
app.include_router(rules_router, prefix=settings.api_prefix)
app.include_router(generation_router, prefix=settings.api_prefix)
app.include_router(review_router, prefix=settings.api_prefix)
app.include_router(quality_router, prefix=settings.api_prefix)
app.include_router(interview_router, prefix=settings.api_prefix)
