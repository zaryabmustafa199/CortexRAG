"""
app/api/v1/auth.py
------------------
Authentication router — register, login, refresh, logout.

Cookie security:
  - Refresh token: HttpOnly, Secure (prod), SameSite=Strict, Path=/auth/refresh
  - Access token: returned in JSON body — stored in memory by frontend (not localStorage)
"""
from __future__ import annotations

from fastapi import APIRouter, Cookie, Depends, Request, Response

from app.core.config import settings
from app.core.deps import get_current_user
from app.core.exceptions import AuthenticationException
from app.db.session import AsyncSessionLocal
from app.models.user import User
from app.schemas.auth import (
    AuthResponse,
    LoginRequest,
    MessageResponse,
    RefreshResponse,
    RegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])

REFRESH_COOKIE_NAME = "cortexrag_refresh"
REFRESH_COOKIE_PARAMS = {
    "key": REFRESH_COOKIE_NAME,
    "httponly": True,
    "secure": settings.is_production,
    "samesite": "strict",
    "path": "/api/v1/auth/refresh",
    "max_age": settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
}


@router.post("/register", response_model=AuthResponse, status_code=201)
async def register(
    body: RegisterRequest,
    response: Response,
) -> AuthResponse:
    """
    Register a new user account.

    - Validates email uniqueness and password complexity (§4.4)
    - Creates User + Profile (free tier) + personal Workspace
    - Returns JWT access token in body + refresh token in HttpOnly cookie
    """
    async with AsyncSessionLocal() as db:
        service = AuthService(db)
        user, access_token, raw_refresh = await service.register(
            email=body.email,
            password=body.password,
        )

    # Set refresh token as HttpOnly cookie with security attributes
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api/v1/auth/refresh",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/login", response_model=AuthResponse)
async def login(
    body: LoginRequest,
    response: Response,
) -> AuthResponse:
    """
    Authenticate with email and password.

    - Brute-force protection: 5 failures → 15-minute lockout
    - Returns JWT access token in body + refresh token in HttpOnly cookie
    """
    async with AsyncSessionLocal() as db:
        service = AuthService(db)
        user, access_token, raw_refresh = await service.login(
            email=body.email,
            password=body.password,
        )

    # Set refresh token as HttpOnly cookie with security attributes
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=raw_refresh,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api/v1/auth/refresh",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return AuthResponse(
        user=UserResponse.model_validate(user),
        access_token=access_token,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/refresh", response_model=RefreshResponse)
async def refresh_token(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=REFRESH_COOKIE_NAME),
) -> RefreshResponse:
    """
    Issue a new access token using the refresh token cookie.

    - Old refresh token is invalidated immediately (rotation)
    - New refresh token set in HttpOnly cookie
    - If refresh token is missing or invalid → 401
    """
    if not refresh_token:
        raise AuthenticationException("Refresh token is missing.")

    async with AsyncSessionLocal() as db:
        service = AuthService(db)
        new_access, new_refresh = await service.refresh(refresh_token)

    # Rotate refresh token cookie with new token
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=new_refresh,
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
        path="/api/v1/auth/refresh",
        max_age=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS * 86400,
    )

    return RefreshResponse(
        access_token=new_access,
        expires_in=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user),
) -> MessageResponse:
    """
    Revoke the current access token and clear the refresh token cookie.

    - Adds access token to Redis blacklist (TTL = remaining token lifetime)
    - Clears the HttpOnly refresh token cookie
    """
    # Extract raw access token from Authorization header
    auth_header = request.headers.get("Authorization", "")
    token = auth_header.removeprefix("Bearer ").strip()

    async with AsyncSessionLocal() as db:
        service = AuthService(db)
        await service.logout(token, str(current_user.id))

    # Clear refresh cookie
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path="/api/v1/auth/refresh",
        httponly=True,
        secure=settings.is_production,
        samesite="strict",
    )

    return MessageResponse(message="Successfully logged out.")
