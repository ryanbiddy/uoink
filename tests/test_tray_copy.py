"""Tray menu labels: one clean line, no hidden accelerators, plain status words."""
import uoink_tray as tray


def test_menu_label_is_one_short_line(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "win32")
    assert tray.menu_label("Q&A talk") == "Q&&A talk"
    assert tray.menu_label("line one\nline two") == "line one line two"
    assert tray.menu_label("   ") == "untitled"
    long = tray.menu_label("a" * 200)
    assert len(long) == 48 and long.endswith("…")


def test_menu_label_leaves_ampersand_alone_off_windows(monkeypatch):
    monkeypatch.setattr(tray.sys, "platform", "darwin")
    assert tray.menu_label("Q&A") == "Q&A"


def test_status_words_are_plain():
    source = open(tray.__file__, encoding="utf-8").read()
    assert "Degraded health!" not in source
    assert "Uoink: Not responding" in source
