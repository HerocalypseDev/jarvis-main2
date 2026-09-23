import os

import jarvis_audio_duck as duck


class FakeVol:
    def __init__(self, muted=0):
        self.muted = muted

    def GetMute(self):
        return self.muted

    def SetMute(self, m, _ctx):
        self.muted = m


def test_mutes_other_apps_while_speaking_and_restores_only_those(monkeypatch):
    music, user_muted, own = FakeVol(0), FakeVol(1), FakeVol(0)
    sessions = [("music", 111, music), ("muted", 222, user_muted), ("jarvis", os.getpid(), own)]
    monkeypatch.setattr(duck, "_sessions", lambda fn: fn(sessions))
    monkeypatch.setenv("JARVIS_DUCK_OTHER_AUDIO", "1")

    duck.duck()
    duck.duck()  # overlapping playback
    assert music.muted == 1 and own.muted == 0
    duck.release(delay=0)
    assert music.muted == 1  # still one playback running
    duck.release(delay=0)
    assert music.muted == 0  # restored
    assert user_muted.muted == 1  # the user's own mute is left alone


def test_off_switch(monkeypatch):
    music = FakeVol(0)
    monkeypatch.setattr(duck, "_sessions", lambda fn: fn([("m", 1, music)]))
    monkeypatch.setenv("JARVIS_DUCK_OTHER_AUDIO", "0")
    duck.duck()
    assert music.muted == 0
    duck.release(delay=0)


def test_opera_gx_music_is_paused_and_resumed(monkeypatch):
    calls = []
    monkeypatch.setattr(duck, "_sessions", lambda fn: fn([]))
    monkeypatch.setattr(duck, "_media", lambda action, ids: calls.append((action, ids)) or (
        ["OperaSoftware.OperaGXWebBrowser.1"] if action == "pause" else []))
    monkeypatch.setenv("JARVIS_DUCK_OTHER_AUDIO", "1")
    monkeypatch.setenv("JARVIS_DUCK_PAUSE_APPS", "OperaGX")

    duck.duck()
    duck.duck()  # nested playback pauses only once
    duck.release(delay=0)
    duck.release(delay=0)
    duck._media_worker.submit(lambda: None).result()  # drain the FIFO worker
    assert calls == [("pause", []), ("resume", ["OperaSoftware.OperaGXWebBrowser.1"])]
    assert duck._paused == []


def test_music_pause_off_when_pattern_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(duck, "_sessions", lambda fn: fn([]))
    monkeypatch.setattr(duck, "_media", lambda action, ids: calls.append(action) or [])
    monkeypatch.setenv("JARVIS_DUCK_OTHER_AUDIO", "1")
    monkeypatch.setenv("JARVIS_DUCK_PAUSE_APPS", "")
    duck.duck()
    duck.release(delay=0)
    duck._media_worker.submit(lambda: None).result()
    assert calls == []
