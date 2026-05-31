from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AgentBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=255)
    system_prompt: str = ""
    model: str = "claude-sonnet-4-6"
    tools: list[str] = []
    channels: list[str] = []
    memory_enabled: bool = False
    guardrails: dict[str, Any] = {}
    limits: dict[str, Any] = {}


class AgentCreate(AgentBase):
    pass


class AgentUpdate(BaseModel):
    """All fields optional — only provided fields are updated (PATCH semantics)."""

    name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=255)
    system_prompt: str | None = None
    model: str | None = None
    tools: list[str] | None = None
    channels: list[str] | None = None
    memory_enabled: bool | None = None
    guardrails: dict[str, Any] | None = None
    limits: dict[str, Any] | None = None


class AgentRead(AgentBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime
    updated_at: datetime
