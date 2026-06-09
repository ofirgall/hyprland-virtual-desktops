from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from vdesk_collapser.config import load_config
from vdesk_collapser.daemon import run_daemon
from vdesk_collapser.driver import Driver, HyprctlDriver
from vdesk_collapser.models import Config
from vdesk_collapser.rules import apply_rules
from vdesk_collapser.snapshot import build_snapshot, snapshot_path, write_snapshot
from vdesk_collapser.transition import run_transition

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vdesk-collapser")
    p.add_argument("--config", default=os.path.expanduser("~/.config/vdesk-collapser/config.toml"))
    p.add_argument("--dry-run", action="store_true", help="log dispatches without executing")
    p.add_argument("--once", action="store_true", help="run a single transition and exit")
    p.add_argument("--simulate", type=int, default=None,
                   help="pretend N monitors are connected (use with --once)")
    p.add_argument("--reorder", action="store_true",
                   help="apply rules for the current profile without transition")
    p.add_argument("--snapshot", action="store_true",
                   help="save current layout as a snapshot and exit")
    p.add_argument("--verbose", "-v", action="store_true")
    return p

def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

log = logging.getLogger("vdesk-collapser")

def run_once_with_simulated_count(
    driver: Driver, cfg: Config, simulated: int, state_dir: Path,
    dry_run: bool = False,
) -> None:
    state_file = state_dir / "state.json"
    current: int | None = None
    if state_file.exists():
        try:
            current = int(json.loads(state_file.read_text()).get("current_profile"))
        except Exception:
            current = None
    if current is None:
        current = len(driver.monitors())
    log.info("current_profile=%d, simulated=%d", current, simulated)
    run_transition(driver, cfg, n_old=current, m_new=simulated,
                   state_dir=state_dir, now_iso=_now_iso(), dry_run=dry_run)

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        return _run(args)
    except subprocess.CalledProcessError as e:
        log.error("command failed: %s (exit %d)", e.cmd, e.returncode)
        return 1
    except Exception:
        log.exception("unexpected error")
        return 1

def _run(args: argparse.Namespace) -> int:
    log.debug("loading config from %s", args.config)
    cfg = load_config(Path(args.config))
    log.debug("config loaded: debounce_ms=%d, profiles=%s", cfg.debounce_ms, list(cfg.profiles.keys()))
    state_dir = Path(os.path.expanduser(cfg.state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(exist_ok=True)
    log.debug("state_dir=%s, dry_run=%s", state_dir, args.dry_run)
    driver: Driver = HyprctlDriver(dry_run=args.dry_run)

    if args.reorder:
        n = len(driver.monitors())
        rules = cfg.profiles.get(n, [])
        log.info("reorder: applying %d rules for profile %d", len(rules), n)
        touched = apply_rules(driver, rules)
        log.info("reorder: touched %d windows", len(touched))
        return 0

    if args.snapshot:
        n = len(driver.monitors())
        snap = build_snapshot(driver, monitor_count=n, now_iso=_now_iso())
        path = snapshot_path(state_dir, n)
        write_snapshot(snap, path)
        state_file = state_dir / "state.json"
        state_file.write_text(json.dumps({"current_profile": n, "transitioning": False}))
        log.info("saved snapshot for profile %d (%d windows) to %s", n, len(snap.windows), path)
        return 0

    if args.once:
        if args.simulate is None:
            print("--once requires --simulate N", file=sys.stderr)
            return 2
        log.debug("--once mode, simulate=%d", args.simulate)
        run_once_with_simulated_count(driver, cfg, args.simulate, state_dir, dry_run=args.dry_run)
        return 0

    if args.simulate is not None:
        print("--simulate only applies with --once", file=sys.stderr)
        return 2

    asyncio.run(run_daemon(Path(args.config), driver=driver))
    return 0

if __name__ == "__main__":
    sys.exit(main())
