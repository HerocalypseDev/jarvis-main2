"""Cascade rules (2026-09-27, executive autonomy): deterministic side effects when Jarvis's state changes.
Data only; jarvis.py maps each action name to a function and audits every run (`cascade` rows).

A rule fires once per transition (the watcher diffs the state every scheduler tick), never every tick.
Add a rule by adding a row here and, if new, an action in jarvis._CASCADE_ACTIONS.
"""

from __future__ import annotations

# (state key, value it changed TO) -> action names, in order
RULES: list[tuple[str, object, str]] = [
    ("sleep", True, "stop_meeting_notes"),         # going to sleep ends any meeting recording
    ("battery", "critical", "stop_meeting_notes"),  # very low battery: stop continuous capture
    ("meeting", True, "hold_announcements"),        # don't talk over (and into) a call being recorded
    ("meeting", False, "release_announcements"),    # read out what waited once it ends
]


class Watcher:
    def __init__(self, rules=None):
        self.rules = list(RULES if rules is None else rules)
        self.last: dict | None = None

    def changes(self, state: dict) -> list[tuple[str, str]]:
        """-> [(event, action)] for every rule whose key changed to its value since the last call. The first
        call only records the state (starting Jarvis is not a transition)."""
        prev, self.last = self.last, dict(state)
        if prev is None:
            return []
        out = []
        for key, value, action in self.rules:
            if key in state and prev.get(key) != state[key] and state[key] == value:
                out.append((f"{key}->{value}", action))
        return out
