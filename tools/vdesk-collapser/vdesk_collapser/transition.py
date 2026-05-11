from __future__ import annotations
import fcntl
import json
from pathlib import Path
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Config
from vdesk_collapser.rules import apply_rules
from vdesk_collapser.snapshot import (
    build_snapshot, write_snapshot, read_snapshot, snapshot_path, replay_snapshot,
)

def _state_file(state_dir: Path) -> Path:
    return state_dir / "state.json"

def run_transition(
    driver: Driver,
    cfg: Config,
    n_old: int,
    m_new: int,
    state_dir: Path,
    now_iso: str,
) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    sfile = _state_file(state_dir)
    sfile.touch(exist_ok=True)
    with open(sfile, "r+") as lockf:
        fcntl.flock(lockf.fileno(), fcntl.LOCK_EX)
        try:
            sfile.write_text(json.dumps({"current_profile": n_old, "transitioning": True}))

            # Step 1: snapshot old profile
            snap_old = build_snapshot(driver, monitor_count=n_old, now_iso=now_iso)
            write_snapshot(snap_old, snapshot_path(state_dir, n_old))

            # Step 2: apply rules for new profile
            rules = cfg.profiles.get(m_new, [])
            touched = apply_rules(driver, rules)

            # Step 3: replay snapshot for new profile (if any), skipping rule-touched
            snap_new = read_snapshot(snapshot_path(state_dir, m_new))
            if snap_new is not None:
                replay_snapshot(driver, snap_new, skip_addresses=touched)

            sfile.write_text(json.dumps({"current_profile": m_new, "transitioning": False}))
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
