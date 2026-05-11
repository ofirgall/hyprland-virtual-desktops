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

def _client_key(c: dict) -> WindowKey:
    return WindowKey(
        klass=c.get("class", ""),
        initial_title=c.get("initialTitle", c.get("title", "")),
        pid=int(c.get("pid", 0)),
    )

def replay_snapshot(driver: Driver, snap: Snapshot, skip_addresses: set[str]) -> None:
    clients = driver.clients()
    by_addr = {c["address"]: c for c in clients}
    by_key: dict[WindowKey, dict] = {_client_key(c): c for c in clients}
    pinned = set(driver.pinned_addresses())
    w2v = driver.workspace_to_vdesk()

    for row in snap.windows:
        live = by_addr.get(row.address) or by_key.get(row.key)
        if live is None:
            continue
        addr = live["address"]
        if addr in skip_addresses:
            continue

        # Unpin first if needed so a subsequent move can take effect.
        if addr in pinned and not row.pinned:
            driver.dispatch("unpinwindow", f"address:{addr}")
            pinned.discard(addr)

        # Move if current vdesk differs (and we aren't currently pinned).
        current_vdesk = w2v.get(live["workspace"]["id"])
        if current_vdesk != row.vdesk and addr not in pinned:
            driver.dispatch("movetodesksilent", f"{row.vdesk},address:{addr}")

        # Pin last if snapshot says pinned but we aren't.
        if row.pinned and addr not in pinned:
            driver.dispatch("pinwindow", f"address:{addr}")
            pinned.add(addr)
