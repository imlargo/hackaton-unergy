"""Space domain model."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class SpaceCreate(BaseModel):
    """Schema for creating a new space."""

    name: str
    space_type: str  # e.g. "room", "office", "kitchen", "garage"
    samples: int = Field(default=20, ge=1, le=100, description="Number of WiFi samples to collect (walk mode)")


class Space(BaseModel):
    """Full space entity as stored in persistence."""

    id: int
    user_id: int
    name: str
    space_type: str
    wifi_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.now)

    model_config = {"from_attributes": True}


class SpaceResponse(BaseModel):
    """Space data returned in API responses."""

    id: int
    user_id: int
    name: str
    space_type: str
    wifi_metadata: dict[str, Any]
    created_at: datetime
