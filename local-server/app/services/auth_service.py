"""Authentication service handling registration, login, and token management."""

import time

from fastapi import HTTPException, status
from jose import jwt
from passlib.context import CryptContext

from app.core.config import settings
from app.domain.user import (
    AuthResponse,
    AuthTokens,
    User,
    UserCreate,
    UserLogin,
    UserResponse,
)
from app.repositories.user_repository import UserRepository

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    """Handles user authentication logic."""

    def __init__(self, user_repo: UserRepository) -> None:
        self._user_repo = user_repo

    def register(self, data: UserCreate) -> AuthResponse:
        """Register a new user and return auth tokens."""
        if self._user_repo.email_exists(data.email):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Email already registered",
            )
        if self._user_repo.username_exists(data.username):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already taken",
            )

        hashed = pwd_context.hash(data.password)
        user = self._user_repo.create(
            username=data.username,
            email=data.email,
            hashed_password=hashed,
        )
        tokens = self._create_tokens(user)
        return AuthResponse(user=self._to_response(user), tokens=tokens)

    def login(self, data: UserLogin) -> AuthResponse:
        """Authenticate a user and return auth tokens."""
        result = self._user_repo.get_by_email(data.email)
        if result is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        user, hashed_password = result
        if not pwd_context.verify(data.password, hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid email or password",
            )

        tokens = self._create_tokens(user)
        return AuthResponse(user=self._to_response(user), tokens=tokens)

    def get_current_user(self, token: str) -> UserResponse:
        """Decode a JWT token and return the associated user."""
        try:
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM]
            )
            user_id: int = payload.get("sub")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token",
                )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )

        user = self._user_repo.get_by_id(int(user_id))
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return self._to_response(user)

    def _create_tokens(self, user: User) -> AuthTokens:
        """Generate access and refresh tokens for a user."""
        expires_at = int(time.time()) + settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        access_payload = {"sub": str(user.id), "exp": expires_at}
        refresh_payload = {"sub": str(user.id), "type": "refresh"}

        access_token = jwt.encode(
            access_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )
        refresh_token = jwt.encode(
            refresh_payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM
        )
        return AuthTokens(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

    @staticmethod
    def _to_response(user: User) -> UserResponse:
        return UserResponse(
            id=user.id,
            email=user.email,
            username=user.username,
            created_at=user.created_at,
            updated_at=user.updated_at,
        )
