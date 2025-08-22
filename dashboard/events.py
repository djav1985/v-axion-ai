from __future__ import annotations
import asyncio

async def pump_events(orchestrator, dbstate, refresh_interval: float = 0.5):
    """
    Purpose: Drive dashboard state without runtime telemetry.
    Polls the orchestrator snapshot periodically and updates the UI state.
    """
    while True:
        await asyncio.sleep(refresh_interval)
        snap = orchestrator.snapshot()
        dbstate.set_snapshot(snap.get("actors", []))
        # No event queue; clear/maintain events via snapshot only
    return None
