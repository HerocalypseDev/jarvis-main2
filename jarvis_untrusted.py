"""Handling of text written by other people (mail, messages, file names, web pages) before it reaches a model.

Always on, dependency-free, shared by the autonomy layer and the sleep-mail replies:

  * `neutralize_injection(text)` -> (safe text, number of phrases removed): canonicalises the text first
    (Unicode NFKC, so full-width letters fold to ASCII; invisible/format characters such as zero-width spaces, soft
    hyphens and bidi overrides are dropped; Cyrillic/Greek look-alike letters inside an otherwise Latin word are
    mapped back), then replaces instruction-like phrases with a placeholder: "ignore previous instructions", "you are
    now (an) admin", "new instructions:", role labels at the start of a line, pseudo tags, "email my files to ...".
    Ordinary appointment text is left alone. The frame markers are defused so a message cannot close its own block.
  * `frame_untrusted(source, sender, text)` wraps text in <<<UNTRUSTED_INBOUND ...>>> ... <<<END_UNTRUSTED_INBOUND>>>.

Pattern matching can never catch every paraphrase; this is one layer (with framing, the higher confidence bar for
third-party text and full logging), not a guarantee.
"""

from __future__ import annotations

import re
import unicodedata

INJECTION_PLACEHOLDER = "[removed: instruction-like text]"

_INJECTION_RES = [re.compile(p, re.I | re.M) for p in (
    r"ignore\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:previous|prior|above|earlier|preceding)\s+(?:instructions?|rules?|prompts?|messages?|context)",
    r"disregard\s+(?:all\s+|any\s+|the\s+|your\s+)?(?:(?:previous|prior|above|earlier)\s+)?(?:instructions?|rules?|prompts?)",
    r"forget\s+(?:everything|all|your)\s+(?:above|previous|prior|instructions?|rules?)",
    r"you\s+are\s+now\s+(?:an?\s+)?(?:ai|assistant|jarvis|dan|developer|admin|administrator|root|unrestricted|free|in\s+\w+\s+mode)\b",
    r"(?:act|behave|respond)\s+as\s+(?:an?\s+)?(?:ai|assistant|jarvis|admin|administrator|root|system|developer)\b",
    r"new\s+(?:system\s+)?instructions?\s*:",
    r"(?:override|bypass)\s+(?:the\s+)?(?:safety|rules?|instructions?|restrictions?|confirmation)",
    r"reveal\s+(?:your\s+|the\s+)?(?:system\s+)?prompt",
    r"^[ \t]*(?:system|assistant|developer|tool)[ \t]*:",
    r"<\s*/?\s*(?:system|assistant|instructions?)\s*>",
    r"\[\s*/?\s*(?:INST|SYS)\s*\]",
    r"(?:send|forward|email)\s+(?:all\s+)?(?:of\s+)?(?:my|the\s+user'?s?)\s+(?:files|passwords?|contacts|emails|data)\b[^\n]*",
)]
_MARKER_RE = re.compile(r"<{3,}|>{3,}")

# Look-alike letters used to spell "ignore" & co. past a filter. Applied only inside a word that ALSO contains
# ASCII letters, so ordinary Russian or Greek text is left untouched.
_CONFUSABLES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ѕ": "s", "ј": "j", "ԁ": "d", "һ": "h", "ԛ": "q", "ԝ": "w",
    "к": "k", "м": "m", "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
    "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I",
    "ο": "o", "α": "a", "ε": "e", "ι": "i", "ν": "v", "ρ": "p", "υ": "u",
    "τ": "t", "κ": "k", "Ο": "O", "Α": "A", "Ε": "E", "Ι": "I", "Ν": "N",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Β": "B", "Η": "H", "Κ": "K", "Μ": "M",
    "Χ": "X", "Ζ": "Z",
})


def _fix_word(m: re.Match) -> str:
    w = m.group(0)
    if any(c.isascii() and c.isalpha() for c in w) and any(ord(c) in _CONFUSABLES for c in w):
        return w.translate(_CONFUSABLES)
    return w


def canonical(text: str) -> str:
    """The text as a human would read it: NFKC, invisible characters removed, look-alike letters folded."""
    s = unicodedata.normalize("NFKC", str(text or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Cf")
    return re.sub(r"\w+", _fix_word, s)


def neutralize_injection(text: str) -> tuple[str, int]:
    """(safe text, number of injection-like phrases removed)."""
    s = _MARKER_RE.sub(lambda m: " ".join(m.group(0)), canonical(text))
    n = 0
    for rx in _INJECTION_RES:
        s, k = rx.subn(INJECTION_PLACEHOLDER, s)
        n += k
    return s, n


def frame_untrusted(source: str, sender: str, text: str) -> str:
    """Wraps text written by someone else so the model can tell data from instructions."""
    who = re.sub(r"[^\w@.+\-]", "", str(sender or ""))[:80] or "unknown"
    src = re.sub(r"[^\w\-]", "", str(source or "message"))[:20] or "message"
    return f"<<<UNTRUSTED_INBOUND source={src} sender={who}>>>\n{text}\n<<<END_UNTRUSTED_INBOUND>>>"
