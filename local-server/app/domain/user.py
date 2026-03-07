"""User domain model."""

from datetime import datetime

from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """Shared user fields."""

    username: str
    email: str


class UserCreate(BaseModel):
    """Schema for user registration."""

    username: str
    email: str
    password: str


class UserLogin(BaseModel):
    """Schema for user login."""

    email: str
    password: str


class User(UserBase):
    """Full user entity as stored in persistence."""

    id: int
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    """User data returned in API responses (no password)."""

    id: int
    email: str
    username: str
    created_at: datetime
    updated_at: datetime


class AuthTokens(BaseModel):
    """JWT token pair."""

    access_token: str
    refresh_token: str
    expires_at: int


class AuthResponse(BaseModel):
    """Full auth response with user and tokens."""

    user: UserResponse
    tokens: AuthTokens
