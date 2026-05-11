from __future__ import annotations
import json
import os
from pathlib import Path
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Snapshot, WindowKey, WindowState

def snapshot_path(state_dir: Path, monitor_count: int) -> Path:
    return state_dir / "snapshots" / f"{monitor_count}.json"

def build_snapshot(driver: Driver, monitor_count: int, now_iso: str) -> Snapshot:
    monitors = {m["id"]: m["name"] for m in driver.monitors()}
    w2v = driver.workspace_to_vdesk()
    pinned = driver.pinned_addresses()
    windows: list[WindowState] = []
    for c in driver.clients():
        ws_id = c["workspace"]["id"]
        if ws_id not in w2v:
            continue
        at = c.get("at", [0, 0])
        size = c.get("size", [0, 0])
        windows.append(
            WindowState(
                key=WindowKey(
                    klass=c.get("class", ""),
                    initial_title=c.get("initialTitle", c.get("title", "")),
                    pid=int(c.get("pid", 0)),
                ),
                address=c["address"],
                vdesk=w2v[ws_id],
                monitor=monitors.get(c.get("monitor"), ""),
                workspace_id=ws_id,
                pinned=c["address"] in pinned,
                floating=bool(c.get("floating", False)),
                at=(int(at[0]), int(at[1])),
                size=(int(size[0]), int(size[1])),
            )
        )
    return Snapshot(monitor_count=monitor_count, taken_at=now_iso, windows=windows)

def write_snapshot(snap: Snapshot, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(snap.to_dict(), indent=2))
    os.replace(tmp, path)

def read_snapshot(path: Path) -> Snapshot | None:
    if not path.exists():
        return None
    return Snapshot.from_dict(json.loads(path.read_text()))
