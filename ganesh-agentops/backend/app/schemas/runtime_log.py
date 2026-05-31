from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

LogLevel = Literal["debug", "info", "warning", "error"]


class RuntimeLogCreate(BaseModel):
    run_id: int | None = None
    level: LogLevel = "info"
    event_type: str | None = None
    message: str = Field(..., min_length=1)
    # Maps to the ORM attribute `log_metadata` (DB column: "metadata")
    log_metadata: dict[str, Any] | None = None


class RuntimeLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    level: str
    event_type: str | None
    message: str
    log_metadata: dict[str, Any] | None
    created_at: datetime
