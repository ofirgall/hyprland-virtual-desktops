from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass(frozen=True)
class WindowKey:
    klass: str
    initial_title: str
    pid: int

@dataclass
class WindowState:
    key: WindowKey
    address: str
    vdesk: int
    monitor: str
    workspace_id: int
    pinned: bool
    floating: bool
    at: tuple[int, int]
    size: tuple[int, int]

@dataclass
class Snapshot:
    monitor_count: int
    taken_at: str
    windows: list[WindowState]
    schema: int = 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "monitor_count": self.monitor_count,
            "taken_at": self.taken_at,
            "windows": [
                {
                    "key": {"class": w.key.klass, "initial_title": w.key.initial_title, "pid": w.key.pid},
                    "address": w.address,
                    "vdesk": w.vdesk,
                    "monitor": w.monitor,
                    "workspace_id": w.workspace_id,
                    "pinned": w.pinned,
                    "floating": w.floating,
                    "at": list(w.at),
                    "size": list(w.size),
                }
                for w in self.windows
            ],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Snapshot":
        return cls(
            schema=d.get("schema", 1),
            monitor_count=d["monitor_count"],
            taken_at=d["taken_at"],
            windows=[
                WindowState(
                    key=WindowKey(w["key"]["class"], w["key"]["initial_title"], w["key"]["pid"]),
                    address=w["address"],
                    vdesk=w["vdesk"],
                    monitor=w["monitor"],
                    workspace_id=w["workspace_id"],
                    pinned=w["pinned"],
                    floating=w["floating"],
                    at=tuple(w["at"]),
                    size=tuple(w["size"]),
                )
                for w in d["windows"]
            ],
        )

@dataclass
class Matcher:
    klass: str | None = None
    title_regex: str | None = None
    initial_class: str | None = None

@dataclass
class Rule:
    match: Matcher
    target_vdesk: int | None = None
    pin: bool | None = None
    distribute: bool | None = None

@dataclass
class Config:
    debounce_ms: int = 1500
    state_dir: str = "~/.local/state/vdesk-collapser"
    profiles: dict[int, list[Rule]] = field(default_factory=dict)
