from pathlib import Path
from vdesk_collapser.config import load_config
from vdesk_collapser.models import Matcher, Rule

SAMPLE = """
[general]
debounce_ms = 800
state_dir = "/tmp/vc"

[[profile.1.rules]]
match.class = "Slack"
target_vdesk = 9
pin = false

[[profile.1.rules]]
match.title_regex = ".* - TMUX$"

[[profile.3.rules]]
match.class = "Slack"
pin = true
"""

def test_load_config_parses_general_and_profiles(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text(SAMPLE)
    cfg = load_config(p)
    assert cfg.debounce_ms == 800
    assert cfg.state_dir == "/tmp/vc"
    assert list(cfg.profiles.keys()) == [1, 3]
    r1 = cfg.profiles[1]
    assert r1[0] == Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)
    assert r1[1] == Rule(match=Matcher(title_regex=".* - TMUX$"))
    assert cfg.profiles[3][0] == Rule(match=Matcher(klass="Slack"), pin=True)

def test_load_config_missing_file_returns_defaults(tmp_path: Path):
    cfg = load_config(tmp_path / "nope.toml")
    assert cfg.debounce_ms == 1500
    assert cfg.profiles == {}

def test_load_config_rejects_unknown_match_field(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[[profile.1.rules]]\nmatch.bogus = "x"\n')
    import pytest
    with pytest.raises(ValueError, match="unknown match field"):
        load_config(p)

def test_load_config_parses_distribute(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[[profile.1.rules]]\nmatch.title_regex = ".* - TMUX$"\ndistribute = true\n')
    cfg = load_config(p)
    assert cfg.profiles[1][0].distribute is True

def test_load_config_rejects_distribute_with_target_vdesk(tmp_path: Path):
    p = tmp_path / "c.toml"
    p.write_text('[[profile.1.rules]]\nmatch.class = "kitty"\ndistribute = true\ntarget_vdesk = 3\n')
    import pytest
    with pytest.raises(ValueError, match="mutually exclusive"):
        load_config(p)
