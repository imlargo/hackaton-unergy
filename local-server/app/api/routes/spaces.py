"""Space management API routes."""

from fastapi import APIRouter, Depends

from app.api.routes.auth import get_current_user
from app.domain.space import SpaceCreate, SpaceResponse
from app.domain.user import UserResponse
from app.services.space_service import SpaceService

router = APIRouter(prefix="/spaces", tags=["spaces"])

_space_service: SpaceService | None = None


def set_space_service(service: SpaceService) -> None:
    global _space_service
    _space_service = service


def get_space_service() -> SpaceService:
    assert _space_service is not None, "SpaceService not initialized"
    return _space_service


@router.post("", response_model=SpaceResponse)
def register_space(
    data: SpaceCreate,
    current_user: UserResponse = Depends(get_current_user),
    space_service: SpaceService = Depends(get_space_service),
):
    """Register a new space using current WiFi environment."""
    return space_service.register_space(user_id=current_user.id, data=data)


@router.get("", response_model=list[SpaceResponse])
def list_spaces(
    current_user: UserResponse = Depends(get_current_user),
    space_service: SpaceService = Depends(get_space_service),
):
    """List all spaces for the current user."""
    return space_service.list_spaces(user_id=current_user.id)


@router.get("/{space_id}", response_model=SpaceResponse)
def get_space(
    space_id: int,
    current_user: UserResponse = Depends(get_current_user),
    space_service: SpaceService = Depends(get_space_service),
):
    """Get a specific space by ID."""
    return space_service.get_space(space_id=space_id, user_id=current_user.id)
