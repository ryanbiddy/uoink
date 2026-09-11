"""Retain Astra's actual browser observation and finish the owned helper hold."""
from pathlib import Path
import datetime as dt
import hashlib
import json

root = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06\c22\artifacts')
files = []
for path in root.glob('*.png'):
    data = path.read_bytes()
    assert data.startswith(b'\x89PNG\r\n\x1a\n')
    files.append({'file': path.name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                  'captured_file_mtime_utc': dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc).isoformat()})
assert len(files) == 6
record = {
    'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'observer': 'Astra',
    'tool': 'agent-browser 0.37.1 local isolated browser session uoink-install06',
    'url': 'http://127.0.0.1:18081/dashboard', 'viewport': [1440, 1100],
    'scope': 'Actual installed browser with original PNG images. Current UTC is in this paired record, not rendered as a product feature.',
    'images': files,
    'reviewed_visible_fields': {
        'source': 'http://c22-fixture.invalid/child-life/feed.xml',
        'consent': 'On (Standing capture), rev 1', 'detection': 'healthy',
        'capture': 'settled failed (worker_lost)', 'enrollment': '1 / 25',
        'starts': '1 / 10 used; 9 remaining',
        'recovery': 'eligible for retry; C22 child-lifetime episode; worker_lost; attempt 1/3; start failed; retry scheduled',
        'activity': '0 running, 0 queued, 0 completed loaded'},
    'browser_page_errors': (root / 'browser-errors.txt').read_text(encoding='utf8').strip(),
    'navigation_observation': [
        'An unquoted PowerShell element ref was refused before a click. The quoted ref worked; no scenario rerun.',
        'Window scrolling did not move the inner content container. All intermediate PNGs are retained. Native DOM scrollTo on the observed main .content exposed the complete card. No CSS, UI text or image bytes were edited.',
        'Automatic command review rejected a combined shell observation-save command before execution, with no reason beyond blocked by policy. Browser error collection and this bounded file serializer were separated; no refused command was executed.'],
    'visual_verdict': 'Consent revision, charge, outcome and recovery fields visibly match the intended fixture. Persisted-state comparison and owned cleanup still required.'}
assert not record['browser_page_errors']
with (root / 'browser-observation-complete.json').open('x', encoding='utf8', newline='\n') as stream:
    stream.write(json.dumps(record, indent=2) + '\n')
print(json.dumps({'images': len(files), 'page_errors': record['browser_page_errors'], 'utc': record['utc']}))
