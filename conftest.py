"""Shared test setup. Personalities (2026-10-06): a personality chosen in the owner's real .env would change the exact
wording many tests check, so every test starts in Classic unless it sets one itself.

Real memory (2026-10-15 recovery audit): several test files imported jarvis or called the autonomy/face/personality
stores without their own temp DB and wrote rows into the repo's real jarvis_memory.db. Every test now starts with
JARVIS_MEMORY_DB_PATH pointing at its own temp file (a test that sets its own still wins), and the import-time default
below covers anything a module does while it is being collected."""

import os
import tempfile
from pathlib import Path

import pytest

os.environ.setdefault("JARVIS_MEMORY_DB_PATH", str(Path(tempfile.mkdtemp(prefix="jarvis-test-")) / "collect.db"))


@pytest.fixture(autouse=True)
def _temp_memory_db(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "jarvis_memory_test.db"))


@pytest.fixture(autouse=True)
def _classic_personality(monkeypatch):
    monkeypatch.setenv("JARVIS_SCHEDULE_STAGGER_S", "0")  # scheduled runs start together in tests unless one sets it
    for key in ("JARVIS_PERSONALITY", "JARVIS_PERSONALITY_SCHEDULE", "JARVIS_PERSONALITY_TIRED_AFTER",
                "JARVIS_VOICE_CLASSIC", "JARVIS_VOICE_PLAYFUL", "JARVIS_VOICE_SERIOUS", "JARVIS_VOICE_GENZ",
                "JARVIS_VOICE_TIRED", "JARVIS_VOICE_HYPE", "JARVIS_VOICE_NAIJA"):
        monkeypatch.delenv(key, raising=False)
