"""Space management API routes (no authentication required)."""

from fastapi import APIRouter, BackgroundTasks, Depends

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
    background_tasks: BackgroundTasks,
    space_service: SpaceService = Depends(get_space_service),
):
    """Register a new space — returns immediately.

    A quick WiFi scan is performed and the space is saved right away.
    Walk-mode fingerprint collection (``samples`` scans, 2 s apart)
    runs **in the background** so the request does not hang.
    Poll ``GET /spaces/{name}/collection-status`` to track progress.
    """
    response = space_service.register_space(user_id=DEFAULT_USER_ID, data=data)

    # Schedule the heavy fingerprint collection in the background
    background_tasks.add_task(
        space_service.run_background_collection,
        space_name=data.name,
        num_samples=data.samples,
    )

    return response


@router.get("", response_model=list[SpaceResponse])
def list_spaces(
    space_service: SpaceService = Depends(get_space_service),
):
    """List all spaces (uses default user, no authentication required)."""
    return space_service.list_spaces(user_id=DEFAULT_USER_ID)


@router.get("/collection-status/{space_name}")
def collection_status(
    space_name: str,
    space_service: SpaceService = Depends(get_space_service),
):
    """Get background fingerprint collection status for a space.

    Returns the current status (collecting / done / error) and
    details like how many fingerprints have been saved and whether
    the ML model was trained.
    """
    status = space_service.get_collection_status(space_name)
    if status is None:
        return {"status": "unknown", "space_name": space_name}
    return {**status, "space_name": space_name}


@router.get("/{space_id}", response_model=SpaceResponse)
def get_space(
    space_id: int,
    space_service: SpaceService = Depends(get_space_service),
):
    """Get a specific space by ID."""
    return space_service.get_space(space_id=space_id, user_id=DEFAULT_USER_ID)


@router.delete("/reset")
def reset_all(
    space_service: SpaceService = Depends(get_space_service),
):
    """Reset everything: delete all spaces, fingerprints, and trained models."""
    return space_service.reset_all()
