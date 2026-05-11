from __future__ import annotations
import asyncio
import datetime as dt
import logging
import os
from pathlib import Path
from typing import Callable
from vdesk_collapser.config import load_config
from vdesk_collapser.debounce import Debouncer
from vdesk_collapser.driver import Driver, HyprctlDriver
from vdesk_collapser.transition import run_transition

log = logging.getLogger("vdesk-collapser")

def _socket_path() -> Path:
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    his = os.environ["HYPRLAND_INSTANCE_SIGNATURE"]
    return Path(runtime) / "hypr" / his / ".socket2.sock"

async def _read_events(path: Path, on_monitor_event: Callable[[], None]) -> None:
    reader, _ = await asyncio.open_unix_connection(str(path))
    while not reader.at_eof():
        line = await reader.readline()
        if not line:
            break
        text = line.decode("utf-8", errors="replace").strip()
        if text.startswith("monitoradded>>") or text.startswith("monitorremoved>>"):
            on_monitor_event()

def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

async def run_daemon(config_path: Path, driver: Driver | None = None) -> None:
    cfg = load_config(config_path)
    state_dir = Path(os.path.expanduser(cfg.state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(exist_ok=True)

    drv: Driver = driver or HyprctlDriver()
    current_profile = len(drv.monitors())
    log.info("starting; current_profile=%d", current_profile)

    async def on_debounce_fire(target_count: int) -> None:
        nonlocal current_profile
        if target_count == current_profile:
            return
        log.info("transition %d -> %d", current_profile, target_count)
        await asyncio.to_thread(
            run_transition,
            drv, cfg, current_profile, target_count, state_dir, _now_iso(),
        )
        current_profile = target_count

    debouncer = Debouncer(delay_s=cfg.debounce_ms / 1000.0, callback=on_debounce_fire)

    def on_monitor_event() -> None:
        debouncer.bump(len(drv.monitors()))

    await _read_events(_socket_path(), on_monitor_event)
