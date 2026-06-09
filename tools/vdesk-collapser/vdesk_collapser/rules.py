from __future__ import annotations
import logging
import re
from vdesk_collapser.driver import Driver
from vdesk_collapser.models import Matcher, Rule

log = logging.getLogger("vdesk-collapser")

def match_window(client: dict, m: Matcher) -> bool:
    if m.klass is not None and client.get("class") != m.klass:
        return False
    if m.initial_class is not None and client.get("initialClass") != m.initial_class:
        return False
    if m.title_regex is not None:
        if not re.search(m.title_regex, client.get("title", "")):
            return False
    return True

def _apply_single(driver: Driver, rule: Rule, c: dict, pinned: set[str], target_vdesk: int | None) -> None:
    addr = c["address"]

    if rule.pin is False and addr in pinned:
        driver.dispatch("unpinwindow", f"address:{addr}")
        pinned.discard(addr)

    if target_vdesk is not None and addr not in pinned:
        driver.dispatch("movetodesksilent", f"{target_vdesk},address:{addr}")

    if rule.pin is True and addr not in pinned:
        driver.dispatch("pinwindow", f"address:{addr}")
        pinned.add(addr)


def apply_rules(driver: Driver, rules: list[Rule]) -> set[str]:
    """Apply rules in declaration order. Returns addresses touched (matched by any rule),
    so the caller can skip them during snapshot replay."""
    touched: set[str] = set()
    clients = driver.clients()
    pinned = set(driver.pinned_addresses())
    w2v = driver.workspace_to_vdesk()

    for rule in rules:
        matched = [c for c in clients if match_window(c, rule.match)]
        if not matched:
            continue

        if rule.distribute and rule.pin is not True:
            matched.sort(key=lambda c: w2v.get(c["workspace"]["id"], 0))
            max_vdesk = max(w2v.values()) if w2v else len(matched)
            for i, c in enumerate(matched):
                vdesk = min(i + 1, max_vdesk)
                addr = c["address"]
                touched.add(addr)
                log.debug("distribute %s (class=%s) -> vdesk %d", addr, c.get("class", "?"), vdesk)
                _apply_single(driver, rule, c, pinned, target_vdesk=vdesk)
        else:
            for c in matched:
                addr = c["address"]
                touched.add(addr)
                log.debug("rule matched %s (class=%s)", addr, c.get("class", "?"))
                _apply_single(driver, rule, c, pinned, target_vdesk=rule.target_vdesk)

    return touched
