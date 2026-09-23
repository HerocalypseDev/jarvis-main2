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
