import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
from fastapi.middleware.cors import CORSMiddleware

from app.api import archives, auth, favorites, household, listings, photos, settings as settings_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    from app.scheduler import start_scheduler, stop_scheduler

    start_scheduler()
    yield
    stop_scheduler()


app = FastAPI(title="Nestswipe", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
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
