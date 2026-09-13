import hashlib
import json
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

root = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
worker = Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\e922b3bf-3d8\gemini')
out = root / 'docs/library/proof/signing-review-02-2026-09-12'
out.mkdir(exist_ok=False)
def put(relative, data):
    dest = out / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open('xb') as stream: stream.write(data)
def copy(relative, path): put(relative, path.read_bytes())

worker_doc = 'docs/library/GEMINI-SIGNING-REVIEW-2026-09-12.md'
copy('worker/original-report.md', worker / worker_doc)
copy('worker/rejected-probes.py.txt', worker / 'tests/test_installer_signing_review.py')
human = root / worker_doc
raw = human.read_text(encoding='utf8')
notice = '> Retained worker report. Read [Astra\'s verdict](ASTRA-SIGNING-REVIEW-02-2026-09-12.md) first: the quoting claim and five proposed regression probes were not accepted. Original bytes are retained in the signing-review-02 proof.\n\n'
human.write_text(notice+'\n'.join(line.rstrip() for line in raw.splitlines())+'\n', encoding='utf8')
sources = ['build.ps1','scripts/installer_signing.ps1','scripts/sign_installer.ps1',
 'tests/test_signing_receipts.py','tests/test_signing_host_selection.py',
 'docs/build-installer.md','docs/library/SIGNING-HOST-REPAIR-BRIEF-2026-09-12.md',
 'docs/library/SIGNING-RECEIPT-REPAIR-BRIEF-2026-09-12.md',
 'docs/library/ASTRA-SIGNING-REVIEW-02-2026-09-12.md']
for name in sources: copy('source/'+name, root / name)
for name in ['check_inno_signing_wiring04.ps1','verify_sdk_signature01.ps1','integrate_signing_review13.py',
 'run_media_verify12.py','integrator_verify.py','seal_signing_review13.py']:
    copy('instruments/'+name, root / '_scratch' / name)
for name in ['signing12-inno-wiring04','signing12-sdk-verification01','signing-review12-integration01']:
    for path in sorted((root / '_scratch' / name).rglob('*')):
        if path.is_file(): copy('observations/'+name+'/'+path.relative_to(root / '_scratch' / name).as_posix(),path)
counts = {}
for label, tree, names in [
 ('checkout',root,['signing-host12-checkout01','signing-receipts12-checkout01','signing-receipts12-checkout02','signing-receipts12-checkout03','signing-review12-checkout01']),
 ('worker',worker,[p.name for p in (worker / '_scratch').glob('signing*') if p.is_dir() and not p.name.endswith('-0')])]:
    for name in names:
        directory = tree / '_scratch' / name
        for path in directory.iterdir():
            if path.is_file(): copy('runs/'+label+'/'+name+'/'+path.name,path)
        guard = directory / 'guard'
        if guard.is_dir():
            for path in guard.glob('*.py'): copy('runs/'+label+'/'+name+'/guard/'+path.name,path)
        report = directory / 'tests.xml'
        if report.is_file():
            suites=ET.parse(report).getroot()
            counts[label+'/'+name] = [s.attrib for s in suites.iter('testsuite')]
put('review.json', (json.dumps({
 'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'worker_reviewed_commit':'d24cc33', 'worker_run':'e922b3bf',
 'counts_from_original_xml':counts, 'existing_tests_modified':False,
 'worker_probes_accepted':False,'uoink_signing_observed':False,'release_ready':False,
 'wiring04_scope':'Direct production callback before the final diagnostic-list addition; compiler refusal, not signing success.',
 'earlier_source_scope':'The receipt01 corrections are described below from the retained edit, not a contemporaneous pre-run source snapshot.'
 },indent=2)+'\n').encode())
put('reconstruction/receipt01-repair-delta.txt', b'File.Replace backup argument: $null -> [NullString]::Value\nCertificate lookup: explicit Microsoft.PowerShell.Security import when Cert drive absent.\nLater addition: capture native SignTool diagnostics and exit in callback receipts.\n')
manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(manifest),'bytes':sum(p.stat().st_size for p in out.rglob('*') if p.is_file()),'test_runs':counts},indent=2))
