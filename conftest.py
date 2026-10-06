"""Shared test setup. Personalities (2026-10-06): a personality chosen in the owner's real .env would change the exact
wording many tests check, so every test starts in Classic unless it sets one itself."""

import pytest


@pytest.fixture(autouse=True)
def _classic_personality(monkeypatch):
    for key in ("JARVIS_PERSONALITY", "JARVIS_PERSONALITY_SCHEDULE", "JARVIS_PERSONALITY_TIRED_AFTER"):
        monkeypatch.delenv(key, raising=False)
