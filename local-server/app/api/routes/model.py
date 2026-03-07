"""Model export/import routes — share trained models between devices.

Allows one PC to export its fingerprints + trained model as a JSON bundle
and another PC to import it, so both can predict locations using the same
model without re-training.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse

from app.services.wifi_integration_service import WiFiIntegrationService

router = APIRouter(prefix="/model", tags=["model"])

_wifi_service: WiFiIntegrationService | None = None


def set_wifi_service(service: WiFiIntegrationService) -> None:
    """Inject the shared WiFiIntegrationService instance."""
    global _wifi_service
    _wifi_service = service


def _svc() -> WiFiIntegrationService:
    assert _wifi_service is not None, "WiFiIntegrationService not wired"
    return _wifi_service


@router.get("/export")
def export_model():
    """Download fingerprints + trained model as a JSON bundle.

    The response is a JSON object that can be saved as a ``.wifipos``
    file and later uploaded on another machine via ``POST /model/import``.
    """
    bundle = _svc().export_bundle()
    if bundle is None:
        return JSONResponse(
            status_code=503,
            content={"error": "WiFi positioning database not available"},
        )
    return bundle


@router.post("/import")
async def import_model(file: UploadFile = File(...)):
    """Upload a previously exported ``.wifipos`` JSON bundle.

    This **replaces** any existing fingerprints and model so the device
    uses the shared data.
    """
    try:
        raw = await file.read()
        bundle = json.loads(raw)
    except Exception as exc:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid bundle file: {exc}"},
        )

    result = _svc().import_bundle(bundle)
    if "error" in result:
        return JSONResponse(status_code=500, content=result)
    return result
