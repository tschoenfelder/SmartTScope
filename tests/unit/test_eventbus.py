import asyncio
import pytest
from smarttscope.services.eventbus import EventBus

@pytest.mark.asyncio
async def test_eventbus_pubsub():
    bus = EventBus()
    got = {}
    bus.subscribe("gps/fix", lambda payload: got.update(payload))
    task = asyncio.create_task(bus.run())
    await bus.publish("gps/fix", {"lat": 50.1})
    await asyncio.sleep(0.01)
    assert got.get("lat") == 50.1
    task.cancel()
