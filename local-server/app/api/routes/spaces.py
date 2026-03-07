"""Space management API routes (no authentication required)."""

from fastapi import APIRouter, Depends

from app.domain.space import SpaceCreate, SpaceResponse
from app.services.space_service import SpaceService

router = APIRouter(prefix="/spaces", tags=["spaces"])

# Default user ID used for all requests (no auth).
DEFAULT_USER_ID = 1

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
    space_service: SpaceService = Depends(get_space_service),
):
    """Register a new space using current WiFi environment."""
    return space_service.register_space(user_id=DEFAULT_USER_ID, data=data)


@router.get("", response_model=list[SpaceResponse])
def list_spaces(
    space_service: SpaceService = Depends(get_space_service),
):
    """List all spaces (uses default user, no authentication required)."""
    return space_service.list_spaces(user_id=DEFAULT_USER_ID)


@router.get("/{space_id}", response_model=SpaceResponse)
def get_space(
    space_id: int,
    space_service: SpaceService = Depends(get_space_service),
):
    """Get a specific space by ID."""
    return space_service.get_space(space_id=space_id, user_id=DEFAULT_USER_ID)
