from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SensorIn(BaseModel):
    sensor_id: str = Field(min_length=1, max_length=50, pattern=r"^[A-Za-z0-9_-]+$")
    type: str = Field(min_length=1, max_length=30)  # e.g. "temperature", "humidity", "vibration"
    unit: str = Field(min_length=1, max_length=10)  # e.g. "C", "%", "mm/s"
    location: Optional[str] = Field(default=None, max_length=100)


class ReadingIn(BaseModel):
    value: float
    # Omit to default to "now" — useful for a live demo. The simulator's
    # backfill mode always sets this explicitly, to spread readings across
    # history instead of writing everything at the current instant.
    ts: Optional[datetime] = None
