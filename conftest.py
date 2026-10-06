"""Shared test setup. Personalities (2026-10-06): a personality chosen in the owner's real .env would change the exact
wording many tests check, so every test starts in Classic unless it sets one itself."""

import pytest


@pytest.fixture(autouse=True)
def _classic_personality(monkeypatch):
    for key in ("JARVIS_PERSONALITY", "JARVIS_PERSONALITY_SCHEDULE", "JARVIS_PERSONALITY_TIRED_AFTER",
                "JARVIS_VOICE_CLASSIC", "JARVIS_VOICE_PLAYFUL", "JARVIS_VOICE_SERIOUS", "JARVIS_VOICE_GENZ",
                "JARVIS_VOICE_TIRED", "JARVIS_VOICE_HYPE", "JARVIS_VOICE_NAIJA"):
        monkeypatch.delenv(key, raising=False)
