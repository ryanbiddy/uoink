"""Observe one original guarded installed-client route with fresh outer evidence."""
from pathlib import Path
import argparse, datetime as dt, hashlib, json, os, stat, subprocess, sys, traceback

p = argparse.ArgumentParser()
p.add_argument('route', choices=('ordinary', 'recall'))
a = p.parse_args()
assert a.route == 'ordinary'
assert sys.flags.isolated and sys.flags.no_site
r = Path(__file__).resolve().parents[1]
root = Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 08')
profile = root / 'p4/profile'
client = profile / 'client'
app = root / 'app'
seal = r / 'docs/library/proof/candidate-package-08-2026-09-12'
package = r / 'build/Uoink-Setup-3.8.0.exe'
claude = Path(r'C:\Users\hello\.local\bin\claude.exe')
record_path = root / 'native-reshelve01-observation.json'
assert not record_path.exists()
for entry in (profile, *profile.parents):
    assert not entry.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
def sha(q):
    with q.open('rb') as stream: return hashlib.file_digest(stream, 'sha256').hexdigest()
def save(q, value):
    with q.open('x', encoding='utf8', newline='\n') as stream:
        stream.write(json.dumps(value, indent=2, default=str) + '\n')

confirmation = json.loads((Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06\p4-client\usage-confirmation.json')).read_text(encoding='utf8'))
assert confirmation['confirmed_by'] == 'Ryan' and confirmation['extra_paid_usage_off'] is True
expected_package = json.loads((seal / 'package-manifest.json').read_text(encoding='utf8'))
assert sha(package) == expected_package['package_sha256']
assert expected_package['build_source'] == 'b8e44fbc0a16950a22b29ead66951fcb80b2d6e8'
for name, row in json.loads((seal / 'SHA256.json').read_text(encoding='utf8'))['files'].items():
    path = (seal / name).resolve(); assert path.is_relative_to(seal)
    assert sha(path) == row['sha256'] and path.stat().st_size == row['bytes']
for row in expected_package['files']:
    assert sha(r / row['source_path']) == row['checkout_and_staged_sha256']
prep = json.loads((client / 'client-config-preparation.json').read_text(encoding='utf8'))
for name, digest in prep['hashes'].items():
    path = (client / name).resolve(); assert path.is_relative_to(client)
    assert sha(path) == digest
launch = json.loads((client / 'launch.json').read_text(encoding='utf8'))
env = os.environ.copy(); env.update(launch['environment']); env['CLAUDE_CONFIG_DIR'] = 'E:\\AI\\projects\\uoink\\installation-receipts\\Agent Install 06\\p4-client\\profile\\client\\claude-config'
for key in ('ANTHROPIC_API_KEY','ANTHROPIC_AUTH_TOKEN','ANTHROPIC_BASE_URL',
            'CLAUDE_CODE_OAUTH_TOKEN','CLAUDE_CODE_OAUTH_TOKEN_FILE_DESCRIPTOR','CLAUDE_CODE_API_KEY_FILE_DESCRIPTOR',
            'CLAUDE_CODE_USE_BEDROCK','CLAUDE_CODE_USE_VERTEX','CLAUDE_CODE_USE_FOUNDRY',
            'OPENAI_API_KEY','XAI_API_KEY','GROK_API_KEY','GEMINI_API_KEY','GOOGLE_API_KEY','UOINK_ISOLATED_APP_DIR'):
    env.pop(key, None)
env.update(IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db',
           HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1')
assert Path(env['CLAUDE_CONFIG_DIR']).resolve() == Path('E:\\AI\\projects\\uoink\\installation-receipts\\Agent Install 06\\p4-client\\profile\\client\\claude-config')
auth_result = subprocess.run([str(claude), 'auth', 'status', '--json'], cwd=client, env=env,
                             capture_output=True, text=True, timeout=30)
assert auth_result.returncode == 0
auth = json.loads(auth_result.stdout)
assert auth['loggedIn'] is True and auth['authMethod'] == 'claude.ai'
safe_auth = {key: auth.get(key) for key in ('loggedIn', 'authMethod', 'subscriptionType')}
auth = auth_result = None
version = subprocess.check_output([str(claude), '--version'], cwd=client, env=env, text=True, timeout=30).strip()
sys.path.insert(0, str(r / 'scripts'))
import install_receipt.manifest as manifest
manifest.CANDIDATE_PACKAGE_02_DIR = seal
from install_receipt.receipt_integrity import verify_installed_bindings
before = verify_installed_bindings(app, manifest.load_candidate_package_02())
assert before['ok']
guard = app / 'python/Lib/site-packages/sitecustomize.py'
assert not guard.exists()
pth_before = {str(q): sha(q) for q in (app / 'python').glob('*._pth')}
prompt = root / 'p4/native-reshelve01-request.txt'
command = [sys.executable, '-I', '-S', '-B', str(r / '_scratch/p4_operator_native_reshelve0108.py'), 'client',
    '--isolated-profile', str(profile), '--isolated-port', '18282', '--installed-app', str(app),
    '--installed-interpreter', str(app / 'python/python.exe'), '--package-manifest', str(seal / 'package-manifest.json'),
    '--receipt-root', str(root / 'p4'), '--package-path', str(package),
    '--source-bindings', str(seal / 'source-bindings.json'), '--forbid-checkout', str(r), '--runtime-mode', 'installed',
    '--client-exe', str(claude), '--prompt-file', str(prompt), '--client-route', a.route,
    '--subscription-confirmed', '--usage-credits-off', '--timeout-seconds', '300']
record = {'started_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'route': a.route,
    'command': command, 'authentication': safe_auth, 'version': version, 'usage_confirmation_sha256': sha(Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 06\p4-client\usage-confirmation.json')),
    'source': expected_package['build_source'], 'package_sha256': sha(package), 'prompt_sha256': sha(prompt),
    'prepared_hashes': prep['hashes'], 'status': 'failed', 'installed_credit': False,
    'instrument_sha256': sha(Path(__file__)), 'bindings_before_ok': before['ok']}
try:
    with (root / 'native-reshelve01-driver.stdout').open('xb') as out, (root / 'native-reshelve01-driver.stderr').open('xb') as err:
        result = subprocess.run(command, cwd=r, env=env, stdout=out, stderr=err, timeout=360)
    record['driver_exit'] = result.returncode
    assert result.returncode == 0, 'Original client route failed; retain it before any further run'
    record['status'] = 'completed_pending_independent_review'
except BaseException as exc:
    record['error'] = type(exc).__name__ + ': ' + str(exc)
finally:
    record['pth_before'] = pth_before
    record['pth_after'] = {str(q): sha(q) for q in (app / 'python').glob('*._pth')}
    record['guard_absent_after'] = not guard.exists()
    record['bindings_after_ok'] = verify_installed_bindings(app, manifest.load_candidate_package_02())['ok']
    if record['pth_before'] != record['pth_after'] or not record['guard_absent_after'] or not record['bindings_after_ok']:
        record.update(status='failed', restoration_error='Exact installed restoration not affirmed')
    record['finished_utc'] = dt.datetime.now(dt.timezone.utc).isoformat()
    save(record_path, record)
print(json.dumps({key: record.get(key) for key in ('route','status','driver_exit','error','guard_absent_after','bindings_after_ok')}, indent=2))
raise SystemExit(0 if record['status'] == 'completed_pending_independent_review' else 1)
