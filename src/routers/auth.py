from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..auth import create_access_token, verify_password
from ..database import get_db
from ..middleware.rate_limit import limiter
from ..models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    token: str
    token_type: str = "bearer"
    expires_in: int = 28800  # 8 hours


@router.post("/token", response_model=TokenResponse, summary="Issue a JWT access token")
@limiter.limit("20/minute")
async def issue_token(
    request: Request,
    body: TokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    result = await db.execute(select(User).where(User.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "INVALID_CREDENTIALS", "message": "Incorrect username or password"},
        )
    return TokenResponse(token=create_access_token(user.id, user.role))
