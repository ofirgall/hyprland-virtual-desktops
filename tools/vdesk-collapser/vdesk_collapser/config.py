from __future__ import annotations
import tomllib
from pathlib import Path
from vdesk_collapser.models import Config, Matcher, Rule

_ALLOWED_MATCH = {"class", "title_regex", "initial_class"}
_ALLOWED_RULE_TOP = {"match", "target_vdesk", "pin"}

def load_config(path: Path) -> Config:
    if not path.exists():
        return Config()
    with open(path, "rb") as f:
        data = tomllib.load(f)

    general = data.get("general", {})
    cfg = Config(
        debounce_ms=int(general.get("debounce_ms", 1500)),
        state_dir=general.get("state_dir", "~/.local/state/vdesk-collapser"),
    )
    profiles_raw = data.get("profile", {})
    for key, body in profiles_raw.items():
        n = int(key)
        rules = []
        for raw in body.get("rules", []):
            extra = set(raw) - _ALLOWED_RULE_TOP
            if extra:
                raise ValueError(f"unknown rule field(s) in profile {n}: {extra}")
            match_raw = raw.get("match", {})
            bad = set(match_raw) - _ALLOWED_MATCH
            if bad:
                raise ValueError(f"unknown match field(s) in profile {n}: {bad}")
            rules.append(
                Rule(
                    match=Matcher(
                        klass=match_raw.get("class"),
                        title_regex=match_raw.get("title_regex"),
                        initial_class=match_raw.get("initial_class"),
                    ),
                    target_vdesk=raw.get("target_vdesk"),
                    pin=raw.get("pin"),
                )
            )
        cfg.profiles[n] = rules
    return cfg
