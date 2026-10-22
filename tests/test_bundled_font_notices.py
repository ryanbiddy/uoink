"""Bundled font notices survive offline regeneration with fixture metadata."""
import importlib.metadata
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "bundled_font_notice_generator", ROOT / "scripts/gen_third_party_notices.py"
)
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


def test_bundled_fonts_match_committed_notices_and_have_licences(tmp_path, monkeypatch):
    rows = [
        {"Name": line.split("==")[0], "Version": line.split("==", 1)[1].split()[0], "License": "fixture"}
        for line in (ROOT / "requirements-installer-lock.txt").read_text().splitlines()
        if line and not line.startswith("#")
    ]
    assert all(not any(char.isspace() for char in row["Version"]) for row in rows)
    monkeypatch.setattr(notices, "_from_pip_licenses", lambda: rows)
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: ())
    target = tmp_path / "notices.md"
    monkeypatch.setattr(notices.sys, "argv", ["notices", str(target)])

    assert notices.main() == 0
    generated = target.read_text(encoding="utf-8")
    committed = (ROOT / "THIRD-PARTY-NOTICES.md").read_text(encoding="utf-8")
    static_start = "## Supplemental upstream notices"
    assert generated[generated.index(static_start):] == committed[committed.index(static_start):]

    heading = "## Bundled fonts (not Python packages)"
    assert generated.count(heading) == 1
    fonts = generated.split(heading, 1)[1]
    assert "SIL Open Font License 1.1" in fonts
    for font, licence in (
        ("Inter", "inter-OFL.txt"),
        ("Bungee", "bungee-OFL.txt"),
        ("JetBrains Mono", "jetbrains-mono-OFL.txt"),
    ):
        assert f"**{font}**" in fonts
        assert f"licence `{licence}`" in fonts
        for folder in ("assets/brand/fonts", "extension/brand/fonts"):
            assert (ROOT / folder / licence).is_file(), f"Missing {folder}/{licence}"
