from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from auth.router import router as auth_router
from core.container import container
from core.exceptions import register_exception_handlers
from templates.router import router as templates_router
from tenants.router import router as tenants_router


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # Order matters: logging must be configured before anything else has a
    # chance to log. `db_engine`/`cache_provider`/`rate_limiter` are called
    # eagerly so a bad DATABASE_URL/REDIS_URL fails fast at startup instead
    # of on first request (see notes in core/container.py). The role cache
    # needs both, so it refreshes last.
    container.logging_configured()
    container.db_engine()
    container.cache_provider()
    container.rate_limiter()
    await container.role_permission_cache_service().refresh()
    yield
    # Graceful shutdown: release the DB pool's and both Redis clients'
    # connections rather than letting the process drop them.
    await container.db_engine().dispose()
    await container.cache_provider().close()
    await container.rate_limiter().close()

def set_api_version(version: str = "v1") -> str:
    return f"/api/{version}"

app = FastAPI(title="Kith", lifespan=lifespan)
register_exception_handlers(app)


app.add_middleware(
    CORSMiddleware,
    allow_origins=container.cors_settings().allowed_origins,
    allow_credentials=True,  # session cookie (ADR-0006)
    allow_methods=["*"],
    allow_headers=["*"],  # must cover X-Tenant-ID + Content-Type
)
app.include_router(auth_router, prefix=set_api_version())
app.include_router(tenants_router, prefix=set_api_version())
app.include_router(templates_router, prefix=set_api_version())


@app.get("/")
async def root() -> dict[str, str]:
    return {"message": "Hello World!"}


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
