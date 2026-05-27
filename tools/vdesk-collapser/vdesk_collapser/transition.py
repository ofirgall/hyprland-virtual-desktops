from __future__ import annotations
import fcntl
import json
import logging
from pathlib import Path
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Config
from vdesk_collapser.rules import apply_rules
from vdesk_collapser.snapshot import (
    build_snapshot, write_snapshot, read_snapshot, snapshot_path, replay_snapshot,
)

log = logging.getLogger("vdesk-collapser")

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
            log.info("transition %d -> %d", n_old, m_new)
            sfile.write_text(json.dumps({"current_profile": n_old, "transitioning": True}))

            snap_old = build_snapshot(driver, monitor_count=n_old, now_iso=now_iso)
            log.info("snapshot profile %d: %d windows", n_old, len(snap_old.windows))
            write_snapshot(snap_old, snapshot_path(state_dir, n_old))

            rules = cfg.profiles.get(m_new, [])
            log.info("applying %d rules for profile %d", len(rules), m_new)
            touched = apply_rules(driver, rules)
            log.info("rules touched %d windows", len(touched))

            snap_new = read_snapshot(snapshot_path(state_dir, m_new))
            if snap_new is not None:
                log.info("replaying snapshot for profile %d (%d windows)", m_new, len(snap_new.windows))
                replay_snapshot(driver, snap_new, skip_addresses=touched)
            else:
                log.info("no snapshot for profile %d, skipping replay", m_new)

            sfile.write_text(json.dumps({"current_profile": m_new, "transitioning": False}))
        finally:
            fcntl.flock(lockf.fileno(), fcntl.LOCK_UN)
