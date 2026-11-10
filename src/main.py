"""
Application entry point.

Startup sequence:
  1. Create all SQLAlchemy tables
  2. Run seed (no-op if data exists)
  3. Mount REST routers under /api/v1/
  4. Mount GraphQL at /graphql
  5. Expose /health and /docs
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from strawberry.fastapi import GraphQLRouter

from .database import Base, engine
from .graphql_api.schema import get_context, schema
from .middleware.rate_limit import limiter, rate_limit_exceeded_handler
from .routers import auth, centers, exams, registrations, slots
from .seed import run_seed


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await run_seed()
    yield


app = FastAPI(
    title="Exam Evaluation & Scheduling System",
    description=(
        "REST + GraphQL API for exam scheduling, geospatial center lookup, "
        "and conflict-aware slot registration. Team APIBP23N."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── Middleware ────────────────────────────────────────────────────────────────
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["RateLimit-Limit", "RateLimit-Remaining", "RateLimit-Reset", "Retry-After"],
)

# ── REST routes ───────────────────────────────────────────────────────────────
for router in (auth.router, exams.router, centers.router, slots.router, registrations.router):
    app.include_router(router, prefix="/api/v1")

# ── GraphQL ───────────────────────────────────────────────────────────────────
graphql_router = GraphQLRouter(schema, context_getter=get_context, graphiql=True)
app.include_router(graphql_router, prefix="/graphql")


# ── Utility endpoints ─────────────────────────────────────────────────────────
@app.get("/health", tags=["ops"], summary="Health check")
async def health():
    return {"status": "ok"}
