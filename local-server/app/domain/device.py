"""Device domain model (placeholder for future implementation).

Devices represent IoT hardware, smart plugs, sensors, etc.
that can be associated with a space for energy monitoring.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    """Schema for registering a new device."""

    space_id: int
    name: str
    device_type: str  # e.g. "smart_plug", "sensor", "meter"
    metadata: dict[str, Any] = Field(default_factory=dict)


class Device(BaseModel):
    """Full device entity."""

    id: int
    space_id: int
    user_id: int
    name: str
    device_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}
