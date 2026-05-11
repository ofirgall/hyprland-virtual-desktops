from __future__ import annotations
import argparse
import asyncio
import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path
from vdesk_collapser.config import load_config
from vdesk_collapser.daemon import run_daemon
from vdesk_collapser.driver import Driver, HyprctlDriver
from vdesk_collapser.models import Config
from vdesk_collapser.transition import run_transition

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="vdesk-collapser")
    p.add_argument("--config", default=os.path.expanduser("~/.config/vdesk-collapser/config.toml"))
    p.add_argument("--dry-run", action="store_true", help="log dispatches without executing")
    p.add_argument("--once", action="store_true", help="run a single transition and exit")
    p.add_argument("--simulate", type=int, default=None,
                   help="pretend N monitors are connected (use with --once)")
    p.add_argument("--verbose", "-v", action="store_true")
    return p

def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).isoformat(timespec="seconds").replace("+00:00", "Z")

def run_once_with_simulated_count(
    driver: Driver, cfg: Config, simulated: int, state_dir: Path,
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
    if current == simulated:
        return
    run_transition(driver, cfg, n_old=current, m_new=simulated,
                   state_dir=state_dir, now_iso=_now_iso())

def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    cfg = load_config(Path(args.config))
    state_dir = Path(os.path.expanduser(cfg.state_dir))
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "snapshots").mkdir(exist_ok=True)
    driver: Driver = HyprctlDriver(dry_run=args.dry_run)

    if args.once:
        if args.simulate is not None:
            run_once_with_simulated_count(driver, cfg, args.simulate, state_dir)
        else:
            current = len(driver.monitors())
            run_once_with_simulated_count(driver, cfg, current, state_dir)
        return 0

    asyncio.run(run_daemon(Path(args.config), driver=driver))
    return 0

if __name__ == "__main__":
    sys.exit(main())
