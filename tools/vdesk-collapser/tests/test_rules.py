from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.models import Matcher, Rule
from vdesk_collapser.rules import match_window, apply_rules

SLACK = {"address": "0x1", "class": "Slack", "title": "Slack | foo", "initialClass": "Slack"}
KITTY = {"address": "0x2", "class": "kitty", "title": "host - TMUX", "initialClass": "kitty"}
FIREFOX = {"address": "0x3", "class": "firefox", "title": "github - Firefox", "initialClass": "firefox"}

def test_match_window_by_class():
    assert match_window(SLACK, Matcher(klass="Slack"))
    assert not match_window(KITTY, Matcher(klass="Slack"))

def test_match_window_by_title_regex():
    assert match_window(KITTY, Matcher(title_regex=r".* - TMUX$"))
    assert not match_window(FIREFOX, Matcher(title_regex=r".* - TMUX$"))

def test_match_window_combined_is_AND():
    m = Matcher(klass="kitty", title_regex=r".* - TMUX$")
    assert match_window(KITTY, m)
    assert not match_window(SLACK, m)

def test_apply_rules_unpin_before_move():
    driver = FakeDriver(clients=[SLACK], pinned={"0x1"})
    rules = [Rule(match=Matcher(klass="Slack"), target_vdesk=9, pin=False)]
    touched = apply_rules(driver, rules)
    assert touched == {"0x1"}
    assert driver.calls == [
        ("unpinwindow", "address:0x1"),
        ("movetodesksilent", "9,address:0x1"),
    ]

def test_apply_rules_pin_after_move():
    driver = FakeDriver(clients=[SLACK], pinned=set())
    rules = [Rule(match=Matcher(klass="Slack"), target_vdesk=2, pin=True)]
    apply_rules(driver, rules)
    assert driver.calls == [
        ("movetodesksilent", "2,address:0x1"),
        ("pinwindow", "address:0x1"),
    ]

def test_apply_rules_idempotent_when_state_matches():
    driver = FakeDriver(clients=[SLACK], pinned={"0x1"})
    rules = [Rule(match=Matcher(klass="Slack"), pin=True)]
    touched = apply_rules(driver, rules)
    assert touched == {"0x1"}
    assert driver.calls == []

def test_apply_rules_returns_addresses_touched():
    driver = FakeDriver(clients=[SLACK, KITTY], pinned=set())
    rules = [Rule(match=Matcher(klass="Slack"), target_vdesk=9)]
    touched = apply_rules(driver, rules)
    assert touched == {"0x1"}
