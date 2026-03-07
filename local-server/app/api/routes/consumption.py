"""Consumption API routes — device management, energy events & carbon footprint.

Allows users to:
- Register devices (TV, lamp, fan, etc.) to a space
- Toggle devices on/off (simulated webhook events)
- View real-time energy consumption per space
- Calculate carbon footprint from consumption data

Device power ratings and carbon factors are mocked but realistic.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/consumption", tags=["consumption"])

# ---------------------------------------------------------------------------
# Mock device catalog — typical watt ratings for common household devices
# ---------------------------------------------------------------------------
DEVICE_CATALOG: dict[str, dict[str, Any]] = {
    "tv": {"label": "Televisor", "watts": 100, "icon": "tv"},
    "lamp": {"label": "Lámpara", "watts": 60, "icon": "lamp"},
    "fan": {"label": "Ventilador", "watts": 75, "icon": "fan"},
    "computer": {"label": "Computador", "watts": 200, "icon": "monitor"},
    "fridge": {"label": "Nevera", "watts": 150, "icon": "refrigerator"},
    "air_conditioner": {"label": "Aire acondicionado", "watts": 1500, "icon": "snowflake"},
    "microwave": {"label": "Microondas", "watts": 1000, "icon": "cooking-pot"},
    "washing_machine": {"label": "Lavadora", "watts": 500, "icon": "shirt"},
    "charger": {"label": "Cargador", "watts": 20, "icon": "battery-charging"},
    "speaker": {"label": "Parlante", "watts": 30, "icon": "speaker"},
}

# Colombia average CO₂ emission factor (kg CO₂ per kWh)
CO2_KG_PER_KWH = 0.126

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
_devices: dict[int, dict[str, Any]] = {}  # id -> device
_events: list[dict[str, Any]] = []  # consumption events log
_next_device_id = 1


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class DeviceCreate(BaseModel):
    space_name: str
    name: str
    device_type: str  # key from DEVICE_CATALOG
    custom_watts: float | None = None  # override default watts


class DeviceToggle(BaseModel):
    device_id: int
    action: str = Field(..., pattern="^(on|off)$")  # "on" or "off"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_device_watts(device: dict) -> float:
    """Return effective watt rating for a device."""
    if device.get("custom_watts"):
        return device["custom_watts"]
    catalog = DEVICE_CATALOG.get(device["device_type"], {})
    return catalog.get("watts", 50)


def _calc_kwh(watts: float, seconds: float) -> float:
    """Convert watts * seconds to kWh."""
    return (watts * seconds) / 3_600_000


def _device_response(d: dict) -> dict:
    """Format device for API response."""
    watts = _get_device_watts(d)
    catalog = DEVICE_CATALOG.get(d["device_type"], {})
    return {
        **d,
        "watts": watts,
        "label": catalog.get("label", d["device_type"]),
        "icon": catalog.get("icon", "plug"),
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/catalog")
def get_device_catalog():
    """Return the catalog of available device types with their specs."""
    return {"devices": DEVICE_CATALOG}


@router.post("/devices")
def register_device(payload: DeviceCreate):
    """Register a new device to a space."""
    global _next_device_id

    if payload.device_type not in DEVICE_CATALOG:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown device_type '{payload.device_type}'. "
                   f"Available: {list(DEVICE_CATALOG.keys())}",
        )

    device = {
        "id": _next_device_id,
        "space_name": payload.space_name,
        "name": payload.name,
        "device_type": payload.device_type,
        "custom_watts": payload.custom_watts,
        "is_on": False,
        "turned_on_at": None,
        "total_kwh": 0.0,
        "created_at": time.time(),
    }
    _devices[_next_device_id] = device
    _next_device_id += 1

    return _device_response(device)


@router.get("/devices")
def list_devices(space_name: str | None = Query(None)):
    """List all registered devices, optionally filtered by space."""
    devices = list(_devices.values())
    if space_name:
        devices = [d for d in devices if d["space_name"] == space_name]
    return {"devices": [_device_response(d) for d in devices]}


@router.post("/event")
def device_event(payload: DeviceToggle):
    """Webhook: toggle a device on or off.

    When turning OFF, calculates energy consumed during the on-period
    and logs a consumption event.
    """
    device = _devices.get(payload.device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Device not found")

    now = time.time()
    watts = _get_device_watts(device)
    event_data: dict[str, Any] = {
        "device_id": device["id"],
        "device_name": device["name"],
        "space_name": device["space_name"],
        "device_type": device["device_type"],
        "action": payload.action,
        "timestamp": now,
        "watts": watts,
    }

    if payload.action == "on":
        device["is_on"] = True
        device["turned_on_at"] = now
        event_data["message"] = (
            f"🔌 {device['name']} encendido en {device['space_name']} "
            f"— consumiendo {watts}W"
        )
    else:  # off
        duration_s = 0.0
        kwh = 0.0
        if device["is_on"] and device["turned_on_at"]:
            duration_s = now - device["turned_on_at"]
            kwh = _calc_kwh(watts, duration_s)
            device["total_kwh"] += kwh
        device["is_on"] = False
        device["turned_on_at"] = None
        event_data["duration_seconds"] = duration_s
        event_data["kwh_consumed"] = round(kwh, 6)
        event_data["co2_kg"] = round(kwh * CO2_KG_PER_KWH, 6)
        event_data["message"] = (
            f"⚡ {device['name']} apagado en {device['space_name']} "
            f"— consumió {kwh:.4f} kWh ({kwh * CO2_KG_PER_KWH:.4f} kg CO₂)"
        )

    _events.append(event_data)
    return event_data


@router.get("/summary")
def consumption_summary(space_name: str | None = Query(None)):
    """Get energy consumption summary with carbon footprint.

    Returns per-device and per-space totals, plus current active power draw.
    """
    devices = list(_devices.values())
    if space_name:
        devices = [d for d in devices if d["space_name"] == space_name]

    now = time.time()
    total_kwh = 0.0
    active_watts = 0.0
    space_totals: dict[str, float] = {}

    device_summaries = []
    for d in devices:
        watts = _get_device_watts(d)
        device_kwh = d["total_kwh"]

        # Add current session consumption if device is on
        if d["is_on"] and d["turned_on_at"]:
            session_seconds = now - d["turned_on_at"]
            device_kwh += _calc_kwh(watts, session_seconds)
            active_watts += watts

        total_kwh += device_kwh
        space_totals[d["space_name"]] = space_totals.get(d["space_name"], 0) + device_kwh

        catalog = DEVICE_CATALOG.get(d["device_type"], {})
        device_summaries.append({
            "id": d["id"],
            "name": d["name"],
            "space_name": d["space_name"],
            "device_type": d["device_type"],
            "label": catalog.get("label", d["device_type"]),
            "is_on": d["is_on"],
            "watts": watts,
            "total_kwh": round(device_kwh, 6),
            "co2_kg": round(device_kwh * CO2_KG_PER_KWH, 6),
        })

    total_co2 = total_kwh * CO2_KG_PER_KWH

    return {
        "total_kwh": round(total_kwh, 6),
        "total_co2_kg": round(total_co2, 6),
        "active_watts": round(active_watts, 2),
        "active_devices": sum(1 for d in devices if d["is_on"]),
        "total_devices": len(devices),
        "co2_factor_kg_per_kwh": CO2_KG_PER_KWH,
        "devices": device_summaries,
        "by_space": {
            space: {
                "kwh": round(kwh, 6),
                "co2_kg": round(kwh * CO2_KG_PER_KWH, 6),
            }
            for space, kwh in space_totals.items()
        },
    }


@router.get("/events")
def list_events(
    space_name: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
):
    """Return recent consumption events (newest first)."""
    events = _events
    if space_name:
        events = [e for e in events if e["space_name"] == space_name]
    return {"events": list(reversed(events[-limit:]))}


@router.get("/active")
def active_devices():
    """Return all currently active (on) devices — useful for alerts."""
    active = [
        _device_response(d)
        for d in _devices.values()
        if d["is_on"]
    ]
    return {
        "active_count": len(active),
        "total_watts": sum(_get_device_watts(d) for d in _devices.values() if d["is_on"]),
        "devices": active,
    }
