from pathlib import Path
from vdesk_collapser.cli import _build_parser, run_once_with_simulated_count
from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.models import Config, Matcher, Rule

def test_parser_accepts_simulate_once_and_dry_run():
    p = _build_parser()
    ns = p.parse_args(["--simulate", "1", "--once", "--dry-run", "--config", "/tmp/c.toml"])
    assert ns.simulate == 1
    assert ns.once is True
    assert ns.dry_run is True
    assert ns.config == "/tmp/c.toml"

def test_run_once_with_simulated_count_drives_transition(tmp_state_dir: Path):
    driver = FakeDriver(
        clients=[{
            "address": "0x1", "class": "Slack", "initialTitle": "Slack", "title": "Slack",
            "pid": 4711, "workspace": {"id": 1}, "monitor": 0,
            "floating": False, "at": [0, 0], "size": [800, 600],
        }],
        monitors=[{"id": 0, "name": "DP-1"}, {"id": 1, "name": "DP-2"}, {"id": 2, "name": "DP-3"}],
        pinned={"0x1"},
        workspace_to_vdesk={1: 1},
    )
    cfg = Config(profiles={1: [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]})
    run_once_with_simulated_count(driver, cfg, simulated=1, state_dir=tmp_state_dir)
    assert ("unpinwindow", "address:0x1") in driver.calls
    assert ("movetodesksilent", "9,address:0x1") in driver.calls
