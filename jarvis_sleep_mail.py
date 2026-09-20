"""Sleep Mode mail take-over.

While Sleep Mode is on, jarvis.py calls run_cycle() every SLEEP_MAIL_INTERVAL_MIN (30) minutes.
One cycle:
  1. Search the Gmail inbox for mail that arrived since Sleep Mode started.
  2. Family (the non-superseded `relationship` facts in Jarvis's memory that carry an email
     address): Jarvis reads the message and replies *as itself* — an assistant who says the user
     is asleep — and keeps the conversation going across cycles. Every reply is recorded for the
     wake-up recap's "important" section. Guardrails: only exact addresses from the family list,
     never the user's own addresses (no self-reply loops), a per-sender cap per night, the reply
     always carries a disclosure signature, and the prompt forbids commitments and private info.
  3. Everyone else: one classification call over sender + subject only; anything critical
     (security alert, payment failure, deadline, emergency) goes in the recap, unanswered.
Sending is retried every minute, up to five more times, if the send errors.

Self-contained like jarvis_sleep_mode.py: talks to Gmail and the model only through callables
jarvis.py passes in, owns two small tables in jarvis_memory.db, never imports jarvis.py.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path

log = logging.getLogger("jarvis.sleep_mail")

SLEEP_MAIL_INTERVAL_MIN = int(os.environ.get("JARVIS_SLEEP_MAIL_INTERVAL_MIN") or 15)
# Once a real message arrives, poll faster for a while so a back-and-forth doesn't crawl.
ACTIVE_INTERVAL_MIN = int(os.environ.get("JARVIS_SLEEP_MAIL_ACTIVE_INTERVAL_MIN") or 2)
ACTIVE_WINDOW_MIN = int(os.environ.get("JARVIS_SLEEP_MAIL_ACTIVE_WINDOW_MIN") or 20)
MAX_ATTACHMENTS = 3
MAX_ATTACHMENT_BYTES = 8 * 1024 * 1024
MAX_ATTACHMENT_TEXT = 6000
_IMAGE_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                ".gif": "image/gif", ".webp": "image/webp"}
_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".log"}
MAX_REPLIES_PER_SENDER = int(os.environ.get("JARVIS_SLEEP_MAIL_MAX_REPLIES") or 6)
SEND_RETRIES = 5  # after the first attempt
SEND_RETRY_DELAY_S = 60
MAX_MESSAGES_PER_CYCLE = 25
USER_NAME = (os.environ.get("JARVIS_USER_NAME") or "Hero").strip() or "Hero"

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
_ERROR_PREFIXES = ("MCP tool call failed", "MCP tool reported an error", "Unknown MCP tool")
_cycle_lock = threading.Lock()


def _db_path() -> Path:
    override = (os.environ.get("JARVIS_MEMORY_DB_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(__file__).resolve().parent / "jarvis_memory.db"


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sleep_mail_handled ("
        "message_id TEXT PRIMARY KEY, sender TEXT, kind TEXT, handled_at TEXT NOT NULL)"
    )
    conn.execute(
        "CREATE TABLE IF NOT EXISTS sleep_mail_replies ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, sleep_started_at TEXT NOT NULL, "
        "sender TEXT NOT NULL, sent_at TEXT NOT NULL, ok INTEGER NOT NULL, body TEXT NOT NULL)"
    )
    return conn


# --- who is family / who is me ---------------------------------------------------------------
def _emails(text: str) -> list[str]:
    return [m.lower() for m in _EMAIL_RE.findall(text or "")]


def _env_set(name: str) -> set[str]:
    return set(_emails(os.environ.get(name) or ""))


def own_addresses() -> set[str]:
    """The user's own addresses: never auto-replied to, so Jarvis can't email itself."""
    out = _env_set("JARVIS_OWN_EMAILS")
    conn = _connect()
    try:
        for (v,) in conn.execute("SELECT value FROM user_profile WHERE key LIKE '%email%'"):
            out.update(_emails(v))
        for (c,) in conn.execute(
            "SELECT content FROM memory_facts WHERE key LIKE 'user_email%' AND superseded_at IS NULL"
        ):
            out.update(_emails(c))
    except sqlite3.OperationalError:
        pass  # tables not created yet
    finally:
        conn.close()
    return out


def _label(content: str) -> str:
    text = re.sub(r"\([^)]*\)", "", content or "")
    text = text.split(", email")[0]
    text = re.sub(r"^\s*\S+'s\s+", "", text).strip()
    return text or "a family member"


def load_family() -> dict[str, str]:
    """{email: label} from current `relationship` facts, minus JARVIS_SLEEP_FAMILY_EXCLUDE and
    the user's own addresses. Read fresh each cycle so editing memory takes effect immediately."""
    blocked = own_addresses() | _env_set("JARVIS_SLEEP_FAMILY_EXCLUDE")
    family: dict[str, str] = {}
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT content FROM memory_facts WHERE category = 'relationship' "
            "AND superseded_at IS NULL"
        ).fetchall()
    except sqlite3.OperationalError:
        rows = []
    finally:
        conn.close()
    for (content,) in rows:
        for addr in _emails(content):
            if addr not in blocked:
                family[addr] = _label(content)
    return family


# --- sending, with retry ---------------------------------------------------------------------
def looks_like_error(result) -> bool:
    return not isinstance(result, str) or result.startswith(_ERROR_PREFIXES)


def send_with_retry(send, retries: int = SEND_RETRIES, delay_s: float = SEND_RETRY_DELAY_S,
                    sleep=time.sleep) -> tuple[bool, str, int]:
    """send() -> (ok, detail). Tries once, then retries every delay_s seconds, up to `retries`
    more times. Returns (ok, last_detail, retries_used)."""
    detail = ""
    for attempt in range(retries + 1):
        try:
            ok, detail = send()
        except Exception as e:  # a send must never crash the cycle
            ok, detail = False, f"{type(e).__name__}: {e}"
        if ok:
            return True, detail, attempt
        log.warning("Sleep-mail send failed (attempt %d/%d): %s", attempt + 1, retries + 1, detail)
        if attempt < retries:
            sleep(delay_s)
    return False, detail, retries


# --- parsing Gmail MCP text output -----------------------------------------------------------
def parse_search(text: str) -> list[dict]:
    """The Gmail MCP's search_emails output is blocks of 'ID:/Subject:/From:/Date:' lines."""
    out = []
    for block in re.split(r"\n\s*\n", text or ""):
        m = {k: re.search(rf"^{k}:\s*(.*)$", block, re.M | re.I) for k in ("ID", "Subject", "From", "Date")}
        if m["ID"] and m["From"]:
            out.append({
                "id": m["ID"].group(1).strip(),
                "subject": (m["Subject"].group(1).strip() if m["Subject"] else "") or "(no subject)",
                "from": m["From"].group(1).strip(),
                "sender": (_emails(m["From"].group(1)) or [""])[0],
            })
    return out


def parse_attachments(read_text: str) -> list[dict]:
    """read_email lists attachments as '- name (mime, N KB, ID: xxx)' under 'Attachments (n):'."""
    out = []
    for m in re.finditer(r"^- (.+?) \(([^,()]+), ([\d.]+) KB, ID: (\S+?)\)\s*$", read_text or "", re.M):
        out.append({"name": m.group(1), "mime": m.group(2).strip(), "kb": float(m.group(3)), "id": m.group(4)})
    return out


def read_attachments(mcp, message_id: str, atts: list[dict]) -> tuple[str, list[dict]]:
    """Downloads (to a throwaway folder, deleted afterwards) and reads what it can. Returns
    (text_for_prompt, extra_content_blocks): text/docx/text-PDF become text; scanned PDFs and
    images become model-readable blocks. Anything else is reported as unreadable, never executed."""
    import base64
    import shutil

    notes: list[str] = []
    blocks: list[dict] = []
    folder = Path(__file__).resolve().parent / ".cache" / "sleep_mail_att" / re.sub(r"\W", "", message_id)
    try:
        for att in atts[:MAX_ATTACHMENTS]:
            name, suffix = att["name"], Path(att["name"]).suffix.lower()
            if att["kb"] * 1024 > MAX_ATTACHMENT_BYTES:
                notes.append(f"[attachment '{name}' is too large to read]")
                continue
            folder.mkdir(parents=True, exist_ok=True)
            res = mcp("download_attachment", {"messageId": message_id, "attachmentId": att["id"],
                                              "filename": Path(name).name, "savePath": str(folder)})
            path = folder / Path(name).name
            if looks_like_error(res) or not path.is_file():
                notes.append(f"[attachment '{name}' could not be downloaded]")
                continue
            try:
                if suffix in _TEXT_SUFFIXES:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                elif suffix == ".docx":
                    import docx
                    text = "\n".join(p.text for p in docx.Document(str(path)).paragraphs)
                elif suffix == ".pdf":
                    text = ""
                    try:
                        import pypdf
                        text = "\n".join((pg.extract_text() or "") for pg in pypdf.PdfReader(str(path)).pages)
                    except Exception as e:
                        log.info("PDF text extraction failed for %s: %s", name, e)
                    if len(text.strip()) < 100:  # scanned/handwritten: let the model read the pages
                        data = base64.standard_b64encode(path.read_bytes()).decode()
                        blocks.append({"type": "text", "text": f"[attached PDF '{name}':]"})
                        blocks.append({"type": "document", "source": {
                            "type": "base64", "media_type": "application/pdf", "data": data}})
                        continue
                elif suffix in _IMAGE_TYPES:
                    data = base64.standard_b64encode(path.read_bytes()).decode()
                    blocks.append({"type": "text", "text": f"[attached image '{name}':]"})
                    blocks.append({"type": "image", "source": {
                        "type": "base64", "media_type": _IMAGE_TYPES[suffix], "data": data}})
                    continue
                else:
                    notes.append(f"[attachment '{name}' ({att['mime']}) is a type I can't read]")
                    continue
                notes.append(f"[attachment '{name}':]\n{text.strip()[:MAX_ATTACHMENT_TEXT]}")
            except Exception as e:
                log.warning("Could not read attachment %s: %s", name, e)
                notes.append(f"[attachment '{name}' could not be read]")
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    if len(atts) > MAX_ATTACHMENTS:
        notes.append(f"[{len(atts) - MAX_ATTACHMENTS} more attachment(s) were not read]")
    return "\n\n".join(notes), blocks


def _body_of(read_text: str) -> tuple[str, str]:
    """(thread_id, body) from read_email output."""
    tid = re.search(r"^Thread ID:\s*(\S+)", read_text or "", re.M | re.I)
    parts = re.split(r"\n\s*\n", read_text or "", maxsplit=1)
    body = parts[1] if len(parts) > 1 else read_text or ""
    body = re.split(r"^Attachments \(\d+\):", body, maxsplit=1, flags=re.M)[0]
    return (tid.group(1) if tid else ""), _strip_quoted(body).strip()[:3000]


def _strip_quoted(body: str) -> str:
    """Drops the quoted earlier thread from a reply: everything from an 'On ... wrote:' line on,
    plus any '>'-prefixed lines, so only what the sender newly wrote reaches the model/recap."""
    kept = []
    for line in (body or "").splitlines():
        if re.match(r"^\s*On .{5,200}wrote:\s*$", line) or re.match(r"^\s*On .{5,120}$", line) and "wrote" in line:
            break
        if line.lstrip().startswith(">"):
            continue
        kept.append(line)
    return "\n".join(kept)


# --- the cycle -------------------------------------------------------------------------------
def _system_prompt(label: str, first_reply: bool) -> str:
    return (
        f"You are Jarvis, the AI assistant of {USER_NAME}. {USER_NAME} is asleep right now and "
        f"cannot reply. You are answering an email from {label}, a family member, on "
        f"{USER_NAME}'s behalf. "
        + ("This is your first reply in this conversation: say clearly that you are Jarvis, "
           f"{USER_NAME}'s assistant, and that {USER_NAME} is asleep. " if first_reply else
           "You have already introduced yourself; do not repeat the introduction. ")
        + f"Never claim to be {USER_NAME}. Refer to {USER_NAME} by name and avoid gendered "
        "pronouns for them. Be warm and brief (under 120 words; up to about 250 if asked to "
        "summarize or explain an attachment), plain text, no markdown. Any attachments the sender "
        "included are provided to you: read and use them; if one could not be read, say so. Have a "
        "real conversation: answer questions and help with what you can. Do NOT commit "
        f"{USER_NAME} to anything (money, plans, meetings, promises, decisions), do not share "
        "private information (passwords, addresses, finances, health details, other people's "
        f"messages), and do not claim to have done any action. If they need something only "
        f"{USER_NAME} can do, say you will flag it for when {USER_NAME} wakes up. If it sounds "
        "like an emergency, urge them to call directly or contact emergency services, and say "
        "you have marked it urgent. Output only the email body."
    )


def _sig_line() -> str:
    return f"— Jarvis, {USER_NAME}'s assistant ({USER_NAME} is asleep; I'll pass this on)"


def _signature() -> str:
    return "\n\n" + _sig_line()


def _is_our_own_message(body: str) -> bool:
    """True if the body carries our signature as an unquoted line. Stops Jarvis answering its own
    reply (when sender and mailbox coincide) or an auto-responder echo; a person's reply that merely
    quotes our signature has it prefixed with '>' and doesn't count."""
    sig = _sig_line()
    return any(line.strip() == sig for line in (body or "").splitlines())


def _handled(conn, mid: str) -> bool:
    return conn.execute("SELECT 1 FROM sleep_mail_handled WHERE message_id = ?", (mid,)).fetchone() is not None


def _mark(conn, mid: str, sender: str, kind: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO sleep_mail_handled VALUES (?, ?, ?, ?)",
        (mid, sender, kind, datetime.now().isoformat(timespec="seconds")),
    )
    conn.commit()


def _classify_critical(claude, others: list[dict]) -> set[int]:
    """One cheap call over sender + subject only (no bodies). Returns indices deemed critical."""
    listing = "\n".join(f"{i}. From: {m['from']} | Subject: {m['subject']}" for i, m in enumerate(others))
    text = claude(
        "You triage a sleeping person's inbox. From the numbered list of senders and subjects, "
        "pick only the CRITICAL ones: security or account-compromise alerts, failed payments or "
        "billing problems, hard deadlines, emergencies, or a real person clearly needing an urgent "
        "reply. Newsletters, promotions and routine notifications are not critical. Answer with a "
        "JSON array of the critical numbers only, e.g. [0, 3], or [] if none.",
        listing, 100,
    ) or ""
    m = re.search(r"\[[\d,\s]*\]", text)
    try:
        return {int(x) for x in json.loads(m.group(0))} if m else set()
    except (ValueError, TypeError):
        return set()


def run_cycle(*, mcp, claude, record, since_iso: str, sleep_started_at: str,
              sleep=time.sleep, test_address: str | None = None, on_inbound=None) -> dict:
    """mcp(tool, args) -> text ('search_emails' etc., un-prefixed); claude(system, user, max_tokens)
    -> text|None; record(text) files an item under the wake-up recap's important section.
    Returns counts, for logging/tests. Skips silently if another cycle is still running."""
    stats = {"seen": 0, "inbound": 0, "family_replied": 0, "family_failed": 0, "critical": 0, "skipped": 0}
    if not _cycle_lock.acquire(blocking=False):
        return stats
    try:
        family, own = load_family(), own_addresses()
        test_address = (test_address or "").strip().lower() or None
        if test_address:
            # Test mode: answer ONLY this one address (even though it's the user's own); ignore
            # real family and everyone else, and leave their mail untouched and unmarked.
            family, own = {test_address: f"{USER_NAME} (testing)"}, set()
        try:
            after = int(datetime.fromisoformat(since_iso).timestamp())
        except ValueError:
            return stats
        found = mcp("search_emails", {"query": f"in:inbox after:{after}", "maxResults": MAX_MESSAGES_PER_CYCLE})
        if looks_like_error(found):
            log.warning("Sleep-mail: Gmail search failed: %s", str(found)[:200])
            return stats
        conn = _connect()
        try:
            others: list[dict] = []
            for msg in parse_search(found):
                if _handled(conn, msg["id"]):
                    continue
                if test_address and msg["sender"] != test_address:
                    continue
                stats["seen"] += 1
                sender = msg["sender"]
                if not sender or sender in own:
                    _mark(conn, msg["id"], sender, "self")
                    stats["skipped"] += 1
                elif sender in family:
                    _handle_family(conn, msg, family[sender], mcp, claude, record, sleep_started_at,
                                   sleep, stats)
                    _mark(conn, msg["id"], sender, "family")
                else:
                    others.append(msg)
                    stats["inbound"] += 1
                    if on_inbound:
                        try:
                            read = mcp("read_email", {"messageId": msg["id"]})
                            msg["body"] = "" if looks_like_error(read) else _body_of(read)[1]  # full body, not just the subject
                            on_inbound(msg)  # e.g. autonomy's event extraction; must never break the cycle
                        except Exception as e:
                            log.warning("Sleep-mail on_inbound hook failed: %s", e)
            if others:
                for i in _classify_critical(claude, others):
                    if 0 <= i < len(others):
                        m = others[i]
                        record(f"Critical email from {m['from']}: \"{m['subject']}\". I did not reply to it.")
                        stats["critical"] += 1
                for m in others:
                    _mark(conn, m["id"], m["sender"], "other")
        finally:
            conn.close()
    finally:
        _cycle_lock.release()
    log.info("Sleep-mail cycle: %s", stats)
    return stats


def _handle_family(conn, msg, label, mcp, claude, record, sleep_started_at, sleep, stats) -> None:
    sender = msg["sender"]
    sent_before = conn.execute(
        "SELECT body FROM sleep_mail_replies WHERE sleep_started_at = ? AND sender = ? AND ok = 1 ORDER BY id",
        (sleep_started_at, sender),
    ).fetchall()
    subject = msg["subject"]
    read = mcp("read_email", {"messageId": msg["id"]})
    thread_id, body = _body_of(read) if not looks_like_error(read) else ("", "")
    if _is_our_own_message(body):
        stats["skipped"] += 1
        return
    stats["inbound"] += 1
    atts = parse_attachments(read) if not looks_like_error(read) else []
    heading = f"{label} emailed you \"{subject}\"" + (
        f" (with attachment: {', '.join(a['name'] for a in atts[:MAX_ATTACHMENTS])})" if atts else "")
    if len(sent_before) >= MAX_REPLIES_PER_SENDER:
        record(f"{heading} again, but I've reached my reply limit for tonight, so you'll want to answer them yourself.")
        stats["skipped"] += 1
        return
    convo = "".join(f"\n[Your earlier reply]: {b[:400]}" for (b,) in sent_before[-3:])
    att_text, blocks = read_attachments(mcp, msg["id"], atts) if atts else ("", [])
    prompt = (f"Email from {label}, subject \"{subject}\":\n{body or '(could not read the body)'}"
              f"{convo}" + (f"\n\n{att_text}" if att_text else ""))
    user = [{"type": "text", "text": prompt}, *blocks] if blocks else prompt
    reply = (claude(_system_prompt(label, first_reply=not sent_before), user, 700) or "").strip()
    if not reply:
        record(f"{heading}, but I couldn't write a reply. It needs your attention.")
        stats["family_failed"] += 1
        return
    full = reply + _signature()

    def _send() -> tuple[bool, str]:
        args = {
            "to": [sender],
            "subject": subject if subject.lower().startswith("re:") else f"Re: {subject}",
            "body": full,
        }
        if thread_id:
            args["threadId"] = thread_id
        res = mcp("send_email", args)
        return (not looks_like_error(res)), str(res)[:200]

    ok, detail, retries_used = send_with_retry(_send, sleep=sleep)
    conn.execute(
        "INSERT INTO sleep_mail_replies (sleep_started_at, sender, sent_at, ok, body) VALUES (?, ?, ?, ?, ?)",
        (sleep_started_at, sender, datetime.now().isoformat(timespec="seconds"), 1 if ok else 0, reply),
    )
    conn.commit()
    snippet = " ".join(body.split())[:200]
    if ok:
        stats["family_replied"] += 1
        record(f"{heading}: {snippet or 'no readable text'}. I told them you're asleep and replied: {reply[:250]}")
    else:
        stats["family_failed"] += 1
        record(f"{heading}: {snippet or 'no readable text'}. I could not send my reply after "
               f"{retries_used + 1} tries ({detail}). It needs your attention.")
