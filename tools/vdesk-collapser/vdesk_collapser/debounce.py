from __future__ import annotations
import asyncio
from typing import Any, Awaitable, Callable

class Debouncer:
    """Calls `callback(latest_value)` once after `delay_s` of quiet."""

    def __init__(self, delay_s: float, callback: Callable[[Any], Awaitable[None]]) -> None:
        self._delay = delay_s
        self._callback = callback
        self._latest: Any = None
        self._task: asyncio.Task | None = None

    def bump(self, value: Any) -> None:
        self._latest = value
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = asyncio.create_task(self._run())

    async def _run(self) -> None:
        try:
            await asyncio.sleep(self._delay)
        except asyncio.CancelledError:
            return
        await self._callback(self._latest)
