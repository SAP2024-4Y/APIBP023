import os
import pytest_asyncio
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from slowapi.errors import RateLimitExceeded

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./data/test_exam_eval.db")
os.environ.setdefault("SECRET_KEY", "test-secret-key")

from src.middleware.rate_limit import limiter, rate_limit_exceeded_handler
from src.database import Base, engine
from src.routers.auth import router as auth_router
from src.routers.exams import router as exams_router
from src.routers.centers import router as centers_router
from src.routers.slots import router as slots_router
from src.routers.registrations import router as registrations_router
from src.graphql_api.schema import get_context, schema
from strawberry.fastapi import GraphQLRouter

app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(exams_router, prefix="/api/v1")
app.include_router(centers_router, prefix="/api/v1")
app.include_router(slots_router, prefix="/api/v1")
app.include_router(registrations_router, prefix="/api/v1")

graphql_app = GraphQLRouter(schema, context_getter=get_context)
app.include_router(graphql_app, prefix="/graphql")


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
