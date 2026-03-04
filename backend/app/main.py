import logging
from contextlib import asynccontextmanager

from ddtrace import config, patch_all

config.fastapi["service_name"] = "nestswipe-backend"
patch_all()

from fastapi import FastAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
from fastapi.middleware.cors import CORSMiddleware

from app.api import archives, auth, favorites, household, listings, photos, settings as settings_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.scheduler import start_scheduler, stop_scheduler

    await start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Nestswipe", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(archives.router, prefix="/api/v1/archives", tags=["archives"])
app.include_router(auth.router, prefix="/api/v1/auth", tags=["auth"])
app.include_router(listings.router, prefix="/api/v1/listings", tags=["listings"])
app.include_router(favorites.router, prefix="/api/v1/favorites", tags=["favorites"])
app.include_router(household.router, prefix="/api/v1/household", tags=["household"])
app.include_router(settings_router.router, prefix="/api/v1/settings", tags=["settings"])
app.include_router(photos.router, prefix="/api/v1/photos", tags=["photos"])


@app.get("/api/v1/health")
async def health():
    return {"status": "ok"}
