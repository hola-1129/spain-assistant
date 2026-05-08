"""Message bus protocol + in-process implementation.

Agents publish/subscribe via Bus, never via direct calls. Today: asyncio queues.
Tomorrow: swap InProcessBus for a Redis/NATS implementation — agent code unchanged.
"""
from __future__ import annotations

import asyncio
from collections import defaultdict
from typing import Any, AsyncIterator, Protocol

from pydantic import BaseModel, ConfigDict, Field

from .tracing import gen_trace_id


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str = Field(default_factory=gen_trace_id)


class Bus(Protocol):
    async def publish(self, msg: Message) -> None: ...
    def subscribe(self, topic: str) -> AsyncIterator[Message]: ...


class InProcessBus:
    def __init__(self) -> None:
        self._queues: dict[str, list[asyncio.Queue[Message]]] = defaultdict(list)

    async def publish(self, msg: Message) -> None:
        for q in self._queues.get(msg.to, []):
            await q.put(msg)

    async def subscribe(self, topic: str) -> AsyncIterator[Message]:
        q: asyncio.Queue[Message] = asyncio.Queue()
        self._queues[topic].append(q)
        try:
            while True:
                yield await q.get()
        finally:
            self._queues[topic].remove(q)
