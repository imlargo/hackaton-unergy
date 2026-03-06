"""Authentication API routes (register, login, me)."""

from fastapi import APIRouter, Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.domain.user import AuthResponse, UserCreate, UserLogin, UserResponse
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])

security = HTTPBearer()

# The actual AuthService instance is injected via dependency override in main.py
_auth_service: AuthService | None = None


def set_auth_service(service: AuthService) -> None:
    global _auth_service
    _auth_service = service


def get_auth_service() -> AuthService:
    assert _auth_service is not None, "AuthService not initialized"
    return _auth_service


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    auth_service: AuthService = Depends(get_auth_service),
) -> UserResponse:
    """Dependency that extracts and validates the current user from JWT."""
    return auth_service.get_current_user(credentials.credentials)


@router.post("/register", response_model=AuthResponse)
def register(data: UserCreate, auth_service: AuthService = Depends(get_auth_service)):
    """Register a new user."""
    return auth_service.register(data)


@router.post("/login", response_model=AuthResponse)
def login(data: UserLogin, auth_service: AuthService = Depends(get_auth_service)):
    """Authenticate user and return tokens."""
    return auth_service.login(data)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: UserResponse = Depends(get_current_user)):
    """Get the current authenticated user."""
    return current_user
