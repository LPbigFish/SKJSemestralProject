from typing import Any

from pydantic import BaseModel


class BrokerMessage(BaseModel):
    action: str
    topic: str | None = None
    payload: Any = None
    message_id: int | None = None


class DeliverMessage(BaseModel):
    action: str = "deliver"
    topic: str
    message_id: int
    payload: Any


class SubscribedMessage(BaseModel):
    action: str = "subscribed"
    topic: str
