from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

import pydantic
from pydantic import ConfigDict, Field


class BaseModel(pydantic.BaseModel):
    model_config = ConfigDict(from_attributes=True)


class UUIDModel(BaseModel):
    id: UUID = Field(default_factory=uuid4)


class TimestampModel(BaseModel):
    created_at: datetime | None = None
    updated_at: datetime | None = None

