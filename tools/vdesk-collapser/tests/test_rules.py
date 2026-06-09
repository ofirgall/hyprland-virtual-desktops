from vdesk_collapser.driver import FakeDriver
from vdesk_collapser.models import Matcher, Rule
from vdesk_collapser.rules import match_window, apply_rules

SLACK = {"address": "0x1", "class": "Slack", "title": "Slack | foo", "initialClass": "Slack", "workspace": {"id": 1}}
KITTY = {"address": "0x2", "class": "kitty", "title": "host - TMUX", "initialClass": "kitty", "workspace": {"id": 3}}
FIREFOX = {"address": "0x3", "class": "firefox", "title": "github - Firefox", "initialClass": "firefox", "workspace": {"id": 2}}

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


def _tmux(addr, ws_id):
    return {"address": addr, "class": "kitty", "title": f"tmux-{addr} - TMUX",
            "initialClass": "kitty", "workspace": {"id": ws_id}}


def test_distribute_assigns_one_per_vdesk_sequentially():
    clients = [_tmux("0xa", 5), _tmux("0xb", 2), _tmux("0xc", 8)]
    w2v = {2: 2, 5: 5, 8: 8}
    driver = FakeDriver(clients=clients, pinned=set(), workspace_to_vdesk=w2v)
    rules = [Rule(match=Matcher(title_regex=r".* - TMUX$"), distribute=True)]
    touched = apply_rules(driver, rules)
    assert touched == {"0xa", "0xb", "0xc"}
    moves = [(cmd, args) for cmd, args in driver.calls if cmd == "movetodesksilent"]
    assert moves == [
        ("movetodesksilent", "1,address:0xb"),
        ("movetodesksilent", "2,address:0xa"),
        ("movetodesksilent", "3,address:0xc"),
    ]


def test_distribute_extras_stack_on_last_vdesk():
    clients = [_tmux("0xa", 1), _tmux("0xb", 2), _tmux("0xc", 3)]
    w2v = {1: 1, 2: 2, 3: 3}
    driver = FakeDriver(clients=clients, pinned=set(), workspace_to_vdesk=w2v)
    rules = [Rule(match=Matcher(title_regex=r".* - TMUX$"), distribute=True)]
    touched = apply_rules(driver, rules)
    moves = [(cmd, args) for cmd, args in driver.calls if cmd == "movetodesksilent"]
    assert moves == [
        ("movetodesksilent", "1,address:0xa"),
        ("movetodesksilent", "2,address:0xb"),
        ("movetodesksilent", "3,address:0xc"),
    ]


def test_distribute_more_windows_than_vdesks():
    clients = [_tmux("0xa", 1), _tmux("0xb", 2), _tmux("0xc", 3), _tmux("0xd", 4)]
    w2v = {1: 1, 2: 2, 3: 3, 4: 3}
    driver = FakeDriver(clients=clients, pinned=set(), workspace_to_vdesk=w2v)
    rules = [Rule(match=Matcher(title_regex=r".* - TMUX$"), distribute=True)]
    apply_rules(driver, rules)
    moves = [(cmd, args) for cmd, args in driver.calls if cmd == "movetodesksilent"]
    assert moves == [
        ("movetodesksilent", "1,address:0xa"),
        ("movetodesksilent", "2,address:0xb"),
        ("movetodesksilent", "3,address:0xc"),
        ("movetodesksilent", "3,address:0xd"),
    ]


def test_distribute_pin_overrides():
    clients = [_tmux("0xa", 1), _tmux("0xb", 2)]
    w2v = {1: 1, 2: 2}
    driver = FakeDriver(clients=clients, pinned=set(), workspace_to_vdesk=w2v)
    rules = [Rule(match=Matcher(title_regex=r".* - TMUX$"), distribute=True, pin=True)]
    apply_rules(driver, rules)
    moves = [(cmd, args) for cmd, args in driver.calls if cmd == "movetodesksilent"]
    assert moves == []
    pins = [(cmd, args) for cmd, args in driver.calls if cmd == "pinwindow"]
    assert len(pins) == 2
