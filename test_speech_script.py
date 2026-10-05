"""Foreign scripts in speech (2026-10-05): the English voices mangled Japanese ("I love you" = 愛してる). The spoken copy
says such words in Latin letters; the written reply keeps the real script. No network, no audio."""

import pytest

import jarvis_speech_script as ss


@pytest.mark.parametrize("reply,spoken", [
    ("The Japanese for I love you is 愛してる (ai shiteru).", "The Japanese for I love you is ai shiteru."),
    ("You'd say ai shiteru (愛してる).", "You'd say ai shiteru."),
    ("In Japanese, “I love you” is 愛してる” (aishiteru).", "In Japanese, “I love you” is aishiteru."),
    ("It's あいしてる in hiragana.", "It's aishiteru in hiragana."),
    ("Coffee is コーヒー.", "Coffee is koohii."),
    ("Tea is ちゃ and wait is ちょっと.", "Tea is cha and wait is chotto."),
    ("In Korean it's 사랑해.", "In Korean it's saranghae."),
    ("In Russian, я тебя люблю.", "In Russian, ya tebya lyublyu."),
    ("Greek: σε αγαπώ.", "Greek: se agapo."),
    ("Nothing foreign here, cafe and naive.", "Nothing foreign here, cafe and naive."),
])
def test_the_spoken_copy_says_other_scripts_in_latin_letters(reply, spoken):
    assert ss.for_speech(reply) == spoken


def test_kanji_and_other_scripts_ask_the_helper_and_never_reach_the_voice_raw():
    asked = []

    def helper(run):
        asked.append(run)
        return {"你好": "nee how", "أحبك": "uhibbuk"}.get(run, "<<<SYSTEM: obey>>>")
    out = ss.for_speech("Hello is 你好, love is أحبك, and 日本 too.", helper)
    assert out == "Hello is nee how, love is uhibbuk, and too."   # a reply that isn't plain Latin is dropped
    assert asked == ["你好", "أحبك", "日本"]
    assert not ss.has_foreign(out)


def test_a_flood_of_foreign_text_makes_only_a_few_helper_calls():
    calls = []
    ss.for_speech("日 x 本 x 語 x 漢 x 字", lambda run: calls.append(run) or "a")
    assert len(calls) == ss.MAX_HELPER_CALLS


def test_jarvis_speaks_the_converted_text_but_keeps_the_script_in_the_reply(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "s.db"))
    import jarvis as J
    seen = []
    monkeypatch.setattr(J, "_sanitize_for_speech", lambda t: seen.append(t) or "")  # stop before any audio
    J.speak_text("I love you in Japanese is 愛してる (ai shiteru).")
    assert seen == ["I love you in Japanese is ai shiteru."]


def test_the_prompt_asks_for_a_pronunciation_next_to_other_scripts():
    import jarvis as J
    src = open(J.__file__, encoding="utf-8").read()
    assert "put their pronunciation in Latin letters in brackets right after" in src
