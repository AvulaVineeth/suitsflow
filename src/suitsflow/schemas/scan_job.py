from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class ScanJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    version_id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    attempts: int
    created_at: datetime
    updated_at: datetime
