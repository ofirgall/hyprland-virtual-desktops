import asyncio
import pytest
from vdesk_collapser.debounce import Debouncer

@pytest.mark.asyncio
async def test_debouncer_fires_after_quiet_period():
    fired: list[int] = []
    async def cb(value: int) -> None:
        fired.append(value)
    d = Debouncer(delay_s=0.05, callback=cb)
    d.bump(1)
    await asyncio.sleep(0.02)
    d.bump(2)
    await asyncio.sleep(0.02)
    d.bump(3)
    assert fired == []
    await asyncio.sleep(0.1)
    assert fired == [3]

@pytest.mark.asyncio
async def test_debouncer_coalesces_rapid_bursts():
    fired: list[int] = []
    async def cb(value: int) -> None:
        fired.append(value)
    d = Debouncer(delay_s=0.03, callback=cb)
    for v in range(10):
        d.bump(v)
        await asyncio.sleep(0.005)
    await asyncio.sleep(0.1)
    assert fired == [9]

@pytest.mark.asyncio
async def test_debouncer_can_fire_multiple_times_with_gaps():
    fired: list[int] = []
    async def cb(value: int) -> None:
        fired.append(value)
    d = Debouncer(delay_s=0.03, callback=cb)
    d.bump(1); await asyncio.sleep(0.1)
    d.bump(2); await asyncio.sleep(0.1)
    assert fired == [1, 2]
