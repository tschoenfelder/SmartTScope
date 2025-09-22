from __future__ import annotations
import asyncio
from collections import defaultdict
from typing import Callable, Dict, Any

class EventBus:
    def __init__(self) -> None:
        self._subs: Dict[str, set[Callable[[Any], None]]] = defaultdict(set)
        self._q: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task | None = None

    def subscribe(self, topic: str, cb: Callable[[Any], None]) -> None:
        self._subs[topic].add(cb)

    def unsubscribe(self, topic: str, cb: Callable[[Any], None]) -> None:
        self._subs[topic].discard(cb)

    async def publish(self, topic: str, payload: Any) -> None:
        await self._q.put((topic, payload))

    async def run(self) -> None:
        while True:
            topic, payload = await self._q.get()
            for cb in list(self._subs[topic]):
                try:
                    cb(payload)
                except Exception:
                    # keep the bus alive even if a callback crashes
                    pass
