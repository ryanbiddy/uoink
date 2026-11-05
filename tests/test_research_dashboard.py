"""Research markup and the offline Node harness used by pytest CI."""
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
PAGE = (ROOT / "assets/dashboard/index.html").read_text(encoding="utf-8")
SCRIPT = PAGE.split("// BEGIN RESEARCH:", 1)[1].split("// END RESEARCH", 1)[0]


class Markup(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.feed(PAGE)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))


def test_research_tab_and_accessible_controls():
    tags = Markup().tags
    assert any(tag == "button" and attrs.get("data-tab-button") == "research" for tag, attrs in tags)
    panel = next(attrs for _, attrs in tags if attrs.get("id") == "tab-research")
    assert panel["data-tab-panel"] == "research" and panel["aria-labelledby"] == "researchHeading"
    for name in ("researchQuestion", "researchMax", "researchAsr", "researchSince", "researchRuns"):
        assert any(tag == "label" and attrs.get("for") == name for tag, attrs in tags)
    progress = next(attrs for _, attrs in tags if attrs.get("id") == "researchProgress")
    assert progress["aria-live"] == "polite" and progress["role"] == "status"
    for name in ("researchCopyPrompt", "researchMarkdown", "researchHtml", "researchShare", "researchCapture"):
        assert any(tag == "button" and attrs.get("id") == name for tag, attrs in tags)
    assert 'research: "research"' in PAGE and "wireResearch();" in PAGE


def test_network_chips_are_the_consent_controls():
    chips = {attrs["data-research-source"]: attrs for _, attrs in Markup().tags if "data-research-source" in attrs}
    assert set(chips) == {"library", "youtube", "podcast", "hn", "hackertube", "reddit"}
    assert "checked" in chips["library"] and "disabled" not in chips["library"]
    assert all("disabled" in attrs for kind, attrs in chips.items() if kind != "library")
    assert "Reddit · coming later" in PAGE
    form = PAGE.split('id="researchForm"', 1)[1].split("</form>", 1)[0]
    for kind in ("youtube", "podcast", "hn", "hackertube"):
        assert chips[kind]["data-research-consent"] == kind
        assert form.count(f'data-research-consent="{kind}"') == 1
        assert PAGE.count(f'data-research-consent="{kind}"') == 2
    assert "Allow YouTube" not in form
    assert "Selecting a source allows" in form
    assert "saveSettingsPatch({ research_network_sources: enabled }, id, renderResearchConsent)" in SCRIPT
    assert 'id="settings-research"' in PAGE


def test_untrusted_run_text_never_enters_html_and_links_are_allowlisted():
    assert not re.search(r"\.innerHTML\s*=|\.outerHTML\s*=|insertAdjacentHTML|\.srcdoc\s*=", SCRIPT)
    assert "node.textContent = String(text)" in SCRIPT
    assert "function researchSafeLink(" in SCRIPT
    for host in ("youtube.com", "www.youtube.com", "youtu.be", "news.ycombinator.com"):
        assert f'"{host}"' in SCRIPT
    assert 'node.target = "_blank"; node.rel = "noopener noreferrer"' in SCRIPT
    assert "callRegistryTool(name, args)" in SCRIPT
    assert "window.setTimeout(refreshResearch, Math.min(5000, remaining))" in SCRIPT
    assert 'state.activeTab === "research" && !document.hidden' in SCRIPT
    assert 'navigator.clipboard.writeText(researchState.view.prompt)' in SCRIPT
    assert '"channel-level attribution"' in SCRIPT and "Didn't make the cut" in SCRIPT


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_research_behavior_in_node():
    result = subprocess.run(["node", str(ROOT / "tests/js/research_dashboard_test.mjs")],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is unavailable")
def test_research_saved_and_new_sources_have_separate_actions():
    result = subprocess.run(["node", str(ROOT / "tests/js/research_dashboard_test.mjs"), "source_actions"],
                            cwd=ROOT, capture_output=True, text=True, encoding="utf-8", timeout=25)
    assert result.returncode == 0, result.stdout + result.stderr
