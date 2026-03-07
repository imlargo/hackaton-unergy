"""Energy event domain model (placeholder for future implementation).

Energy events represent consumption readings, spikes, or patterns
detected at a specific space or device.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class EnergyEventCreate(BaseModel):
    """Schema for recording an energy event."""

    space_id: int
    device_id: int | None = None
    event_type: str  # e.g. "consumption_reading", "spike", "anomaly"
    value: float
    unit: str = "kWh"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EnergyEvent(BaseModel):
    """Full energy event entity."""

    id: int
    space_id: int
    device_id: int | None = None
    user_id: int
    event_type: str
    value: float
    unit: str = "kWh"
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}
