"""Tracking API routes — start/stop continuous location prediction."""

from fastapi import APIRouter, Depends, Query

from app.services.wifi_integration_service import WiFiIntegrationService

router = APIRouter(prefix="/tracking", tags=["tracking"])

_wifi_service: WiFiIntegrationService | None = None


def set_wifi_service(service: WiFiIntegrationService) -> None:
    global _wifi_service
    _wifi_service = service


def get_wifi_service() -> WiFiIntegrationService:
    assert _wifi_service is not None, "WiFiIntegrationService not initialized"
    return _wifi_service


@router.post("/start")
def start_tracking(
    interval: float = Query(default=3.0, ge=1.0, le=30.0, description="Seconds between predictions"),
    wifi_service: WiFiIntegrationService = Depends(get_wifi_service),
):
    """Start continuous location tracking (background thread).

    Equivalent to ``wifipos track --interval N``.
    The latest prediction is available via GET /tracking/status.
    """
    return wifi_service.start_tracking(interval=interval)


@router.post("/stop")
def stop_tracking(
    wifi_service: WiFiIntegrationService = Depends(get_wifi_service),
):
    """Stop continuous location tracking."""
    return wifi_service.stop_tracking()


@router.get("/status")
def tracking_status(
    wifi_service: WiFiIntegrationService = Depends(get_wifi_service),
):
    """Get current tracking state and latest prediction."""
    return wifi_service.get_tracking_status()


@router.get("/predict")
def predict_once(
    wifi_service: WiFiIntegrationService = Depends(get_wifi_service),
):
    """Perform a single location prediction (no continuous tracking needed)."""
    return wifi_service.get_current_location()
