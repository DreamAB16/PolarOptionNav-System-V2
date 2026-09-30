"""FastAPI entry point for the bridge decision-support API."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config.settings import settings
from backend.app.routes import router

app = FastAPI(title=settings.app_name, version="0.1.0", description="Polar navigation decision-support API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)


@app.get("/", tags=["system"])
def root() -> dict[str, str]:
    """Return a lightweight service health response."""

    return {"system": settings.app_name, "status": "running"}
