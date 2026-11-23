"""Compile each dashboard script separately, as the browser does."""
from html.parser import HTMLParser
import json
from pathlib import Path
import shutil
import subprocess

import pytest


class InlineScripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []
        self.current = None

    def handle_starttag(self, tag, attrs):
        if tag == "script" and "src" not in dict(attrs):
            self.current = []
            self.scripts.append((self.getpos()[0], self.current))

    def handle_data(self, data):
        if self.current is not None:
            self.current.append(data)

    def handle_endtag(self, tag):
        if tag == "script":
            self.current = None


def test_every_dashboard_inline_script_parses():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is unavailable")
    dashboard = Path(__file__).resolve().parents[1] / "assets/dashboard/index.html"
    parser = InlineScripts()
    parser.feed(dashboard.read_text(encoding="utf-8"))
    parser.close()
    assert parser.current is None, "Unclosed inline <script> in dashboard"
    assert parser.scripts, "No inline scripts found in dashboard"
    program = """
        const fs = require('node:fs');
        const vm = require('node:vm');
        for (const [line, parts] of JSON.parse(fs.readFileSync(0, 'utf8'))) {
            new vm.Script(parts.join(''), {filename: 'assets/dashboard/index.html', lineOffset: line - 1});
        }
    """
    result = subprocess.run([node, "-e", program], input=json.dumps(parser.scripts),
                            capture_output=True, text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
