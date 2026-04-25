from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .db import close_pool, init_pool
from .routers import auth, distros, ingest, install, packages, projects, search, suggestions


@asynccontextmanager
async def lifespan(_: FastAPI):
    await init_pool()
    yield
    await close_pool()


app = FastAPI(
    title="LPS API",
    version="0.1.0",
    description="Linux Package Search — unified search across distros.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


app.include_router(search.router, prefix="/api/v1")
app.include_router(projects.router, prefix="/api/v1")
app.include_router(packages.router, prefix="/api/v1")
app.include_router(distros.router, prefix="/api/v1")
app.include_router(install.router, prefix="/api/v1")
app.include_router(suggestions.router, prefix="/api/v1")
app.include_router(auth.router, prefix="/api/v1")
app.include_router(ingest.router, prefix="/api/v1")
