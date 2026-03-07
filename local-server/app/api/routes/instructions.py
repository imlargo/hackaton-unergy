"""Instructions API route for space registration guidance."""

from fastapi import APIRouter, Depends

from app.services.wifi_integration_service import WiFiIntegrationService

router = APIRouter(prefix="/instructions", tags=["instructions"])

_wifi_service: WiFiIntegrationService | None = None


def set_wifi_service(service: WiFiIntegrationService) -> None:
    global _wifi_service
    _wifi_service = service


def get_wifi_service() -> WiFiIntegrationService:
    assert _wifi_service is not None, "WiFiIntegrationService not initialized"
    return _wifi_service


@router.get("/register-space")
def get_register_space_instructions(
    wifi_service: WiFiIntegrationService = Depends(get_wifi_service),
):
    """Get step-by-step instructions for registering a new space."""
    return {
        "title": "Cómo registrar un espacio",
        "description": (
            "Sigue estos pasos para registrar un nuevo espacio "
            "usando el sistema de posicionamiento WiFi."
        ),
        "steps": wifi_service.get_setup_instructions(),
    }


@router.get("/wifi-status")
def get_wifi_status(
    wifi_service: WiFiIntegrationService = Depends(get_wifi_service),
):
    """Check if WiFi scanning is available and return a sample scan."""
    scan_result = wifi_service.scan_current_environment()
    return {
        "wifi_available": scan_result.get("source") != "mock",
        "source": scan_result.get("source", "unknown"),
        "networks_detected": scan_result.get("networks_detected", 0),
    }
