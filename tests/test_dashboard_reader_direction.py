"""Reader direction invariants; rendered layout is checked by the strict browser gate."""
from pathlib import Path
import re


DASHBOARD = (Path(__file__).resolve().parents[1] / "assets/dashboard/index.html").read_text(encoding="utf-8")
CSS = re.sub(r"/\*.*?\*/", "", DASHBOARD.split("<style>", 1)[1].split("</style>", 1)[0], flags=re.S)
MARKUP = DASHBOARD.split("<script>", 1)[0]
RULES = [(" ".join(selector.split()), body) for selector, body in re.findall(r"([^{}]+)\{([^{}]*)\}", CSS)]


def test_reader_chrome_has_no_washes_glow_or_headline_word_swaps():
    assert "radial-gradient" not in CSS
    assert "text-shadow:" not in CSS
    assert "drop-shadow(" not in CSS
    app = next(body for selector, body in RULES if selector == ".app")
    assert "background: var(--bg);" in app
    headings = re.findall(r"<h1\b[^>]*>(.*?)</h1>", MARKUP, re.S)
    assert headings and all(not re.search(r"<(?:em|i)\b", heading) for heading in headings)
    assert not re.search(r"font-family:[^;]*(?:Georgia|Times New Roman)", CSS)


def test_monospace_is_reserved_for_raw_error_lines():
    mono = {selector for selector, body in RULES if "font-family: var(--font-mono)" in body}
    assert mono == {".activity-error-line", ".source-recovery-reason"}
    assert "font-family:monospace" not in DASHBOARD


def test_library_search_and_captures_precede_draft_resume_and_insights():
    positions = [MARKUP.index(f'id="{name}"') for name in
                 ("searchInput", "libraryGrid", "resumeCard", "libraryInsights")]
    assert positions == sorted(positions)
    assert MARKUP.count('id="resumeCard"') == 1


def test_only_reader_toast_and_steps_have_motion():
    animated = set()
    for selector, body in RULES:
        declarations = re.findall(r"(?:^|;)\s*(?:animation|transition)(?:-[\w-]+)?\s*:\s*([^;]+)", body)
        if declarations and any(value.strip() != "none" for value in declarations):
            # The global reduced-motion override is part of the foundation gate.
            if selector != "*, *::before, *::after":
                animated.add(selector)
    # The busy-button spinner (UI review 2026-10-31) is the one control that
    # moves; the global reduced-motion rule stops it like the rest.
    assert animated == {".step.now.advanced", ".tab-panel.reader.active", ".toast", ".toast.show",
                        '.button[aria-busy="true"]::before'}
