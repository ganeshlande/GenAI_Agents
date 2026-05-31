from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MessageType = Literal["text", "tool_call", "tool_result", "system", "error"]
ChannelType = Literal["internal", "telegram", "slack", "whatsapp"]


class MessageCreate(BaseModel):
    run_id: int | None = None
    sender_agent: str | None = None
    receiver_agent: str | None = None
    channel: ChannelType = "internal"
    content: str = Field(..., min_length=1)
    message_type: MessageType = "text"


class MessageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    run_id: int | None
    sender_agent: str | None
    receiver_agent: str | None
    channel: str
    content: str
    message_type: str
    created_at: datetime
