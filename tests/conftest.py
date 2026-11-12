import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test_exam_eval.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.database import Base, engine
from src.main import app


@pytest_asyncio.fixture(scope="session")
async def client():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    from src.seed import run_seed
    await run_seed()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="session")
async def token(client: AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/auth/token",
        json={"username": "demo", "password": "demo-password"},
    )
    assert resp.status_code == 200
    return resp.json()["token"]
