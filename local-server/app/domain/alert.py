"""Alert domain model (placeholder for future implementation).

Alerts represent notifications triggered by energy events,
unusual patterns, or carbon footprint thresholds.
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AlertCreate(BaseModel):
    """Schema for creating an alert."""

    space_id: int
    alert_type: str  # e.g. "high_consumption", "anomaly", "carbon_threshold"
    severity: str = "info"  # "info", "warning", "critical"
    message: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class Alert(BaseModel):
    """Full alert entity."""

    id: int
    space_id: int
    user_id: int
    alert_type: str
    severity: str = "info"
    message: str
    is_read: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}
