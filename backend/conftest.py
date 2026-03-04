import os

# Must be set before any app imports
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("JWT_SECRET", "test-secret-key")
os.environ.setdefault("MINIO_ENDPOINT", "localhost:9000")
os.environ.setdefault("MINIO_ROOT_USER", "test")
os.environ.setdefault("MINIO_ROOT_PASSWORD", "test")
os.environ.setdefault("DD_TRACE_ENABLED", "false")

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from jose import jwt
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.listing import Listing, ListingPhoto
from app.models.user import Household, User


@pytest_asyncio.fixture
async def db_engine():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    # Enable foreign keys for SQLite
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(db_engine):
    factory = async_sessionmaker(db_engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def test_user(db_session):
    household = Household(name="Test Household")
    db_session.add(household)
    await db_session.flush()

    user = User(
        google_id="test-google-id",
        email="test@example.com",
        name="Test User",
        household_id=household.id,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
def auth_headers(test_user):
    token = jwt.encode(
        {"sub": str(test_user.id)},
        os.environ["JWT_SECRET"],
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def sample_listing(db_session, test_user):
    """Create a listing with a photo (required for queue visibility)."""
    listing = Listing(
        household_id=test_user.household_id,
        user_id=test_user.id,
        source="seloger",
        source_id="123456",
        title="Test Apartment",
        price=500000,
        sqm=60,
        price_per_sqm=8333.33,
        bedrooms=2,
        rooms=3,
        city="Paris",
        district="Marais",
    )
    db_session.add(listing)
    await db_session.flush()

    photo = ListingPhoto(
        listing_id=listing.id,
        s3_key="photos/test.jpg",
        original_url="https://example.com/photo.jpg",
        position=0,
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(listing)
    return listing
