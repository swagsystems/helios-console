from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
FORGE_CSS = (ROOT / "css" / "forge.css").read_text()


def test_mobile_context_chips_wrap_without_horizontal_or_vertical_blowout():
    assert ".forge-mobile-context {" in FORGE_CSS
    assert "flex-wrap: wrap;" in FORGE_CSS
    assert "overflow-x: visible;" in FORGE_CSS
    assert ".forge-mobile-context .forge-chip" in FORGE_CSS
    assert "max-width: 100%;" in FORGE_CSS


def test_mobile_chat_keeps_a_real_scroll_viewport_for_long_logs():
    assert ".forge-chat {" in FORGE_CSS
    assert "min-height: 360px;" in FORGE_CSS
    assert "@media (max-width: 420px)" in FORGE_CSS
    assert "flex-basis: 360px;" in FORGE_CSS


def test_mobile_tool_and_approval_cards_do_not_keep_desktop_indents():
    assert ".forge-tool," in FORGE_CSS
    assert ".forge-inline-approval {" in FORGE_CSS
    assert "margin-left: 0;" in FORGE_CSS
    assert ".forge-tool-row {" in FORGE_CSS
    assert "align-items: flex-start;" in FORGE_CSS
