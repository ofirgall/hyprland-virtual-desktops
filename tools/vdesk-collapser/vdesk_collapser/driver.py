from __future__ import annotations
import json
import re
import subprocess
from typing import Protocol

class Driver(Protocol):
    def clients(self) -> list[dict]: ...
    def monitors(self) -> list[dict]: ...
    def pinned_addresses(self) -> set[str]: ...
    def workspace_to_vdesk(self) -> dict[int, int]: ...
    def dispatch(self, command: str, args: str) -> None: ...

class HyprctlDriver:
    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run

    def _json(self, *args: str) -> list[dict] | dict:
        out = subprocess.check_output(["hyprctl", "-j", *args], text=True)
        return json.loads(out)

    def clients(self) -> list[dict]:
        return self._json("clients")  # type: ignore[return-value]

    def monitors(self) -> list[dict]:
        return self._json("monitors")  # type: ignore[return-value]

    def pinned_addresses(self) -> set[str]:
        # plugin command "printpinnedwindows" returns plain text, one address per line
        out = subprocess.check_output(["hyprctl", "printpinnedwindows"], text=True)
        addrs: set[str] = set()
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("0x"):
                addrs.add(line.split()[0])
        return addrs

    def workspace_to_vdesk(self) -> dict[int, int]:
        # plugin "printstate" returns lines like "vdesk 1: workspace 1 (monitor DP-1), ..."
        out = subprocess.check_output(["hyprctl", "printstate"], text=True)
        mapping: dict[int, int] = {}
        for line in out.splitlines():
            m = re.match(r"\s*vdesk\s+(\d+)\s*:", line)
            if not m:
                continue
            vdesk = int(m.group(1))
            for ws in re.findall(r"workspace\s+(\d+)", line):
                mapping[int(ws)] = vdesk
        return mapping

    def dispatch(self, command: str, args: str) -> None:
        if self.dry_run:
            print(f"[dry-run] hyprctl dispatch {command} {args}")
            return
        subprocess.check_call(["hyprctl", "dispatch", command, args])


class FakeDriver:
    def __init__(
        self,
        clients: list[dict] | None = None,
        monitors: list[dict] | None = None,
        pinned: set[str] | None = None,
        workspace_to_vdesk: dict[int, int] | None = None,
    ) -> None:
        self._clients = clients or []
        self._monitors = monitors or []
        self._pinned = set(pinned or set())
        self._w2v = dict(workspace_to_vdesk or {})
        self.calls: list[tuple[str, str]] = []

    def clients(self) -> list[dict]:
        return self._clients

    def monitors(self) -> list[dict]:
        return self._monitors

    def pinned_addresses(self) -> set[str]:
        return self._pinned

    def workspace_to_vdesk(self) -> dict[int, int]:
        return self._w2v

    def dispatch(self, command: str, args: str) -> None:
        self.calls.append((command, args))
        # mirror simple state mutations so subsequent reads in the same test see effects
        if command == "pinwindow":
            addr = args.split("address:", 1)[1] if "address:" in args else None
            if addr:
                self._pinned.add(addr)
        elif command == "unpinwindow":
            addr = args.split("address:", 1)[1] if "address:" in args else None
            if addr:
                self._pinned.discard(addr)
