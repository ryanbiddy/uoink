"""Packaging and notices must retain a declared runtime system package."""
import importlib.util
import json
from pathlib import Path
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runtime_notice_probe', ROOT / 'scripts/gen_third_party_notices.py')
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


def test_runtime_notice_generation_includes_setuptools_and_excludes_build_tools(tmp_path, monkeypatch):
    rows = [{'Name': line.split('==')[0], 'Version': line.split('==')[1], 'License': 'fixture'}
            for line in (ROOT / 'requirements-installer-lock.txt').read_text().splitlines()
            if line and not line.startswith('#')]
    rows += [{'Name': name, 'Version': 'fixture'} for name in ('pip', 'wheel', 'pip-licenses', 'prettytable')]
    def collect(command, **kwargs):
        assert '--with-system' in command, 'pip-licenses otherwise omits setuptools'
        return json.dumps(rows)
    monkeypatch.setattr(notices.subprocess, 'check_output', collect)
    output = tmp_path / 'notices.md'
    monkeypatch.setattr(notices.sys, 'argv', ['notices', str(output)])
    assert notices.main() == 0
    text = output.read_text(encoding='utf8')
    assert '| setuptools | 83.0.0 |' in text
    assert '| torch | 2.8.0 |' in text
    for name in ('pip', 'wheel', 'pip-licenses', 'prettytable'):
        assert f'| {name} |' not in text


def test_missing_runtime_notice_fails_before_writing(tmp_path, monkeypatch):
    monkeypatch.setattr(notices, '_from_pip_licenses', lambda: [{'Name': 'torch'}])
    output = tmp_path / 'notices.md'
    monkeypatch.setattr(notices.sys, 'argv', ['notices', str(output)])
    with pytest.raises(RuntimeError, match='Missing runtime notices:.*setuptools'):
        notices.main()
    assert not output.exists()


def test_actual_trim_patterns_keep_setuptools_startup_support():
    build = (ROOT / 'build.ps1').read_text(encoding='utf8')
    block = build.split('$stripGlobs = @(', 1)[1].split('\n)', 1)[0]
    patterns = re.findall(r'"\$StagingDir\\python\\Lib\\site-packages\\([^"\\]+)"', block)
    assert patterns
    from fnmatch import fnmatchcase
    for entry in ('setuptools', 'setuptools-83.0.0.dist-info', '_distutils_hack', 'distutils-precedence.pth'):
        assert not any(fnmatchcase(entry, pattern) for pattern in patterns), entry
    for entry in ('pip', 'pip-26.1.2.dist-info', 'wheel', '__pycache__'):
        assert any(fnmatchcase(entry, pattern) for pattern in patterns), entry
