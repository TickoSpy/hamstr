import asyncio
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.services.paths import STORAGE_SUBDIRS


@pytest.fixture
def storage_root(tmp_path, monkeypatch):
    """Point storage at a temp dir. `settings` is a module-level singleton read at
    call time by storage_dir() and _file_response(), so patching the instance works."""
    monkeypatch.setattr(settings, "storage_root", tmp_path)
    for sub in STORAGE_SUBDIRS:
        (tmp_path / sub).mkdir(parents=True, exist_ok=True)
    return tmp_path


@pytest_asyncio.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
    async with SessionLocal() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    app.state.download_queue = asyncio.Queue()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    app.dependency_overrides.clear()
