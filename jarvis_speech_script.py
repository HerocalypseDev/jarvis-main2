"""Foreign scripts in speech (2026-10-05, owner report: "the Japanese for I love you" was pronounced wrong and
weirdly). Jarvis's voices are English voices, so text in another writing system (Japanese, Chinese, Korean, Arabic,
Russian...) comes out mangled. The SPOKEN copy says it in Latin letters instead; the dashboard/phone keep the real
script. Owner's choice: Latin letters with the same voice, for every non-Latin script.

Order, per run of foreign text:
  1. a pronunciation the reply already gives in brackets ("愛してる (ai shiteru)") is used, the script dropped;
     a bracket holding only the script ("ai shiteru (愛してる)") is dropped;
  2. kana, Hangul, Cyrillic and Greek are converted here exactly (tables, no package);
  3. anything else (kanji/Chinese characters, Arabic, Hindi...) goes to `helper(run)` (a tiny AI call in jarvis.py);
  4. if that gives nothing usable the run is left out: silence beats noise.
A local Japanese dictionary (pykakasi) was tried and rejected: it read 愛してる as "itoshi teru".
Pure module: no jarvis import, no network.
"""

from __future__ import annotations

import re

_FOREIGN = (
    "Ͱ-ϿЀ-ԯ԰-֏֐-׿؀-ۿ܀-ࣿऀ-෿฀-໿"
    "ༀ-࿿က-႟Ⴀ-ჿᄀ-ᇿក-៿々぀-ヿ㄀-ㄯ"
    "㄰-㆏ㇰ-ㇿ㐀-䶿一-鿿ꥠ-꥿가-힯ힰ-퟿豈-﫿"
    "ｦ-ﾟ"
)
_F = f"[{_FOREIGN}]"
_SEP = r"[\s　-〄〆-〿・！-／：-＠]"
_RUN_RE = re.compile(f"{_F}(?:{_SEP}*{_F})*")
_HAS_FOREIGN = re.compile(_F)
_BRACKET_ONLY_FOREIGN = re.compile(rf"\s*[(（]\s*{_F}(?:{_SEP}*{_F})*\s*[)）]")
_AFTER_BRACKET = re.compile(r"[\"'”’」』]?\s*[(（]\s*([^()（）]{1,80}?)\s*[)）]")
_LATIN_OK = re.compile(r"^[A-Za-zÀ-ɏ][A-Za-zÀ-ɏ' .,\-]*$")
MAX_HELPER_CALLS = 3  # per spoken text: one odd reply must never turn into a burst of model calls

# --- kana -> Hepburn ---------------------------------------------------------------------------------------------
_KANA = {
    "あ": "a", "い": "i", "う": "u", "え": "e", "お": "o", "か": "ka", "き": "ki", "く": "ku", "け": "ke", "こ": "ko",
    "さ": "sa", "し": "shi", "す": "su", "せ": "se", "そ": "so", "た": "ta", "ち": "chi", "つ": "tsu", "て": "te",
    "と": "to", "な": "na", "に": "ni", "ぬ": "nu", "ね": "ne", "の": "no", "は": "ha", "ひ": "hi", "ふ": "fu",
    "へ": "he", "ほ": "ho", "ま": "ma", "み": "mi", "む": "mu", "め": "me", "も": "mo", "や": "ya", "ゆ": "yu",
    "よ": "yo", "ら": "ra", "り": "ri", "る": "ru", "れ": "re", "ろ": "ro", "わ": "wa", "ゐ": "i", "ゑ": "e", "を": "o",
    "ん": "n", "が": "ga", "ぎ": "gi", "ぐ": "gu", "げ": "ge", "ご": "go", "ざ": "za", "じ": "ji", "ず": "zu",
    "ぜ": "ze", "ぞ": "zo", "だ": "da", "ぢ": "ji", "づ": "zu", "で": "de", "ど": "do", "ば": "ba", "び": "bi",
    "ぶ": "bu", "べ": "be", "ぼ": "bo", "ぱ": "pa", "ぴ": "pi", "ぷ": "pu", "ぺ": "pe", "ぽ": "po", "ゔ": "vu",
    "ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o", "ゃ": "ya", "ゅ": "yu", "ょ": "yo", "ゎ": "wa",
}
_YOON = {"ゃ": "a", "ゅ": "u", "ょ": "o"}
_SMALL_VOWEL = {"ぁ": "a", "ぃ": "i", "ぅ": "u", "ぇ": "e", "ぉ": "o"}


def _hira(ch: str) -> str:
    o = ord(ch)
    return chr(o - 0x60) if 0x30A1 <= o <= 0x30F6 else ch  # katakana -> hiragana


def kana_to_romaji(text: str) -> str:
    chars = [_hira(c) for c in text]
    out: list[str] = []
    double_next = False
    i = 0
    while i < len(chars):
        c = chars[i]
        if c == "っ":
            double_next = True
            i += 1
            continue
        if c == "ー":  # long-vowel mark: repeat the last vowel
            prev = "".join(out)
            if prev and prev[-1] in "aeiou":
                out.append(prev[-1])
            i += 1
            continue
        syl = _KANA.get(c)
        if syl is None:
            out.append(" " if c.isspace() or not c.isalnum() else c)
            i += 1
            continue
        nxt = chars[i + 1] if i + 1 < len(chars) else ""
        if nxt in _YOON and syl.endswith("i") and len(syl) > 1:
            base = syl[:-1]
            syl = (base if base in ("sh", "ch", "j") else base + "y") + _YOON[nxt]
            i += 1
        elif nxt in _SMALL_VOWEL and syl in ("fu", "vu", "te", "de", "u", "shi", "chi", "ji", "tsu"):
            base = {"fu": "f", "vu": "v", "te": "t", "de": "d", "u": "w", "shi": "sh", "chi": "ch", "ji": "j",
                    "tsu": "ts"}[syl]
            syl = base + _SMALL_VOWEL[nxt]
            i += 1
        if double_next:
            syl = ("t" + syl) if syl.startswith("ch") else (syl[0] + syl)
            double_next = False
        out.append(syl)
        i += 1
    return re.sub(r"\s+", " ", "".join(out)).strip()


# --- Hangul -> Revised Romanization (syllable by syllable; sound-change rules left out) -----------------------------
_L = ["g", "kk", "n", "d", "tt", "r", "m", "b", "pp", "s", "ss", "", "j", "jj", "ch", "k", "t", "p", "h"]
_V = ["a", "ae", "ya", "yae", "eo", "e", "yeo", "ye", "o", "wa", "wae", "oe", "yo", "u", "wo", "we", "wi", "yu", "eu",
      "ui", "i"]
_T = ["", "k", "k", "k", "n", "n", "n", "t", "l", "k", "m", "l", "l", "l", "p", "l", "m", "p", "p", "t", "t", "ng", "t",
      "t", "k", "t", "p", "t"]


def hangul_to_latin(text: str) -> str:
    out = []
    for ch in text:
        o = ord(ch) - 0xAC00
        if 0 <= o < 11172:
            out.append(_L[o // 588] + _V[(o % 588) // 28] + _T[o % 28])
        else:
            out.append(" " if not ch.isalnum() else "")
    return re.sub(r"\s+", " ", "".join(out)).strip()


_CYR = dict(zip("абвгдеёжзийклмнопрстуфхцчшщъыьэюяіїєґ",
                ["a", "b", "v", "g", "d", "e", "yo", "zh", "z", "i", "y", "k", "l", "m", "n", "o", "p", "r", "s", "t",
                 "u", "f", "kh", "ts", "ch", "sh", "shch", "", "y", "", "e", "yu", "ya", "i", "yi", "ye", "g"]))
_GREEK = dict(zip("αβγδεζηθικλμνξοπρσςτυφχψωάέήίόύώϊϋΐΰ",
                  ["a", "v", "g", "d", "e", "z", "i", "th", "i", "k", "l", "m", "n", "x", "o", "p", "r", "s", "s", "t",
                   "i", "f", "ch", "ps", "o", "a", "e", "i", "i", "o", "i", "o", "i", "i", "i", "i"]))


def _by_table(text: str, table: dict) -> str:
    out = []
    for ch in text:
        low = ch.lower()
        if low in table:
            out.append(table[low])
        else:
            out.append(" " if not ch.isalnum() else "")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _only(run: str, lo: int, hi: int, extra: str = "") -> bool:
    return all(lo <= ord(c) <= hi or c in extra or re.match(_SEP, c) for c in run)


def convert_run(run: str) -> str | None:
    """Exact local conversion for the scripts that need no dictionary; None for the rest (kanji, Arabic...)."""
    kana = all(0x3040 <= ord(c) <= 0x30FF or re.match(_SEP, c) for c in run)
    if kana:
        return kana_to_romaji(run) or None
    if _only(run, 0xAC00, 0xD7AF):
        return hangul_to_latin(run) or None
    if _only(run, 0x0400, 0x052F):
        return _by_table(run, _CYR) or None
    if _only(run, 0x0370, 0x03FF):
        return _by_table(run, _GREEK) or None
    return None


def clean_pronunciation(text, run: str = "") -> str | None:
    """A model's answer is used only if it is plain Latin letters of a sensible length."""
    t = re.sub(r"\s+", " ", str(text or "")).strip().strip("\"'.").strip()
    if not t or _HAS_FOREIGN.search(t) or not _LATIN_OK.match(t) or len(t) > 3 * len(run) + 30:
        return None
    return t


def has_foreign(text: str) -> bool:
    return bool(_HAS_FOREIGN.search(text or ""))


def for_speech(text: str, helper=None) -> str:
    """The text as it should be SPOKEN: every run of another script replaced by Latin letters (see module doc)."""
    if not text or not _HAS_FOREIGN.search(text):
        return text
    t = _BRACKET_ONLY_FOREIGN.sub("", text)  # "ai shiteru (愛してる)" -> "ai shiteru"
    out, pos, calls = [], 0, 0
    for m in _RUN_RE.finditer(t):
        out.append(t[pos:m.start()])
        run = m.group(0).strip()
        end = m.end()
        after = _AFTER_BRACKET.match(t, end)
        said = None
        if after and not _HAS_FOREIGN.search(after.group(1)) and re.search(r"[A-Za-z]", after.group(1)):
            said, end = after.group(1).strip(), after.end()  # "愛してる (ai shiteru)" -> "ai shiteru"
        if said is None:
            said = convert_run(run)
        if said is None and helper is not None and calls < MAX_HELPER_CALLS:
            calls += 1
            try:
                said = clean_pronunciation(helper(run), run)
            except Exception:
                said = None
        out.append(said or "")
        pos = end
    out.append(t[pos:])
    return re.sub(r"\s+([,.!?;:])", r"\1", re.sub(r"[ \t]{2,}", " ", "".join(out))).strip()
