from __future__ import annotations
import re
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Matcher, Rule

def match_window(client: dict, m: Matcher) -> bool:
    if m.klass is not None and client.get("class") != m.klass:
        return False
    if m.initial_class is not None and client.get("initialClass") != m.initial_class:
        return False
    if m.title_regex is not None:
        if not re.search(m.title_regex, client.get("title", "")):
            return False
    return True

def apply_rules(driver: Driver, rules: list[Rule]) -> set[str]:
    """Apply rules in declaration order. Returns addresses touched (matched by any rule),
    so the caller can skip them during snapshot replay."""
    touched: set[str] = set()
    clients = driver.clients()
    pinned = set(driver.pinned_addresses())

    for rule in rules:
        for c in clients:
            if not match_window(c, rule.match):
                continue
            addr = c["address"]
            touched.add(addr)

            # A: unpin first if rule wants unpinned and currently pinned
            if rule.pin is False and addr in pinned:
                driver.dispatch("unpinwindow", f"address:{addr}")
                pinned.discard(addr)

            # B: move (no-op if currently pinned — Hyprland ignores moves on pinned windows)
            if rule.target_vdesk is not None and addr not in pinned:
                driver.dispatch("movetodesksilent", f"{rule.target_vdesk},address:{addr}")

            # C: pin last if rule wants pinned and not yet pinned
            if rule.pin is True and addr not in pinned:
                driver.dispatch("pinwindow", f"address:{addr}")
                pinned.add(addr)

    return touched
