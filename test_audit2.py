"""Second full audit (2026-10-04). One test per defect found; temp DB only, no network, no real hardware."""

import pytest


@pytest.fixture
def J(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_MEMORY_DB_PATH", str(tmp_path / "a2.db"))
    import jarvis as j
    j._command_ctx.untrusted_origin = False
    yield j
    j._command_ctx.untrusted_origin = False


def test_an_email_started_task_cannot_drive_the_screen_or_whatsapp(J):
    """mcp_windows_* was blocked for untrusted runs, but the built-in screen tools (read/click/scroll/close windows)
    and the WhatsApp tools were not: an injected email could still read the screen or message someone as the owner."""
    J._command_ctx.untrusted_origin = True
    try:
        for name in ("read_screen", "click_at", "scroll_screen", "control_window",
                     "mcp_whatsapp_browser_type", "mcp_whatsapp_browser_snapshot"):
            assert J._untrusted_block(name), name
        assert J._untrusted_block("create_reminder") is None
    finally:
        J._command_ctx.untrusted_origin = False
    assert J._untrusted_block("read_screen") is None  # the owner's own commands are unaffected


def test_claims_about_closing_tabs_or_turning_off_a_skill_need_a_tool_behind_them(J):
    """The claim checker had no entry for tabs/windows, and "clear those" didn't know skills/monitoring/routines, so
    "I've closed the YouTube tab" or "I've cancelled your billing monitoring" with nothing run went unchallenged."""
    assert J._unbacked_claims("I've closed the YouTube tab.", []) == ["close that"]
    assert J._unbacked_claims("I've closed the YouTube tab.", ["browser_tabs"]) == []
    assert J._unbacked_claims("Done, I've cancelled your billing monitoring.", []) == ["clear those"]
    assert J._unbacked_claims("I've turned off that skill.", ["skills"]) == []
    assert J._unbacked_claims("I've turned off that skill.", []) == ["clear those"]
    assert J._unbacked_claims("Shall I close the other tabs?", []) == []
    assert J._unbacked_claims("You have 4 tabs open in Opera GX.", []) == []
