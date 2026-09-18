from typing import Literal

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]
    environment: Literal["local", "test", "staging", "production"]
