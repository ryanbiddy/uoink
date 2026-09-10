"""Seal a reviewed actual-install observation; preserve raw statuses and omit private stores."""
import argparse,hashlib,json,os,shutil,stat
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--summary',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 05')
out=a.out.resolve();assert out.is_relative_to(r/'_scratch') or out==r/'docs/library/proof/ryan-agent-installed-05-2026-09-09'
summary=json.loads(a.summary.read_text(encoding='utf8'))
assert summary['setup_observed'] is True
package=json.loads((r/'docs/library/proof/candidate-package-05-2026-09-09/package-manifest.json').read_text())
assert summary['package_sha256']==package['package_sha256']
for stage in ('install','same-version-reinstall'):
 raw=json.loads((root/(stage+'.json')).read_text())
 assert raw['package_sha256']==package['package_sha256'] and raw['exit']==0
 assert (root/(stage+'.shortcuts.json')).exists()
out.mkdir(exist_ok=False)
excluded=[]
def copy(src,rel):
 assert src.is_relative_to(root) or src.is_relative_to(r/'_scratch')
 assert not src.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT
 target=out/rel;target.parent.mkdir(parents=True,exist_ok=True)
 shutil.copyfile(src,target)
for q in root.iterdir():
 if q.is_file() and q.suffix in ('.json','.stdout','.stderr','.log','.inf'):copy(q,Path('observation')/q.name)
copy(root/'app/isolated-install.json',Path('observation/installed-marker.json'))
for stage in ('install','same-version-reinstall'):
 q=root/(stage+'-temp')/'uoink-install-verify.log'
 copy(q,Path('observation')/(stage+'-files-only.log'))
c22=root/'c22'
for q in c22.iterdir():
 if q.is_file() and (q.suffix=='.json' or q.name=='journal.jsonl'):copy(q,Path('c22')/q.name)
for folder in ('commands','evidence','artifacts'):
 for q in (c22/folder).rglob('*'):
  if q.is_file() and q.suffix in ('.json','.jsonl','.log','.png','.jpg'):copy(q,Path('c22')/q.relative_to(c22))
for q in (c22/'profiles').glob('*/c22-guard-events.jsonl'):copy(q,Path('c22')/q.relative_to(c22))
p4=root/'p4-02/profile'
for folder,label in [(root/'p4/profile','p4-first-failed'),(p4,'p4')]:
 for base,dirs,files in os.walk(folder):
  dirs[:]=[name for name in dirs if name not in ('claude-config','tmp','__pycache__')]
  for name in files:
   q=Path(base)/name;rel=q.relative_to(folder)
   if name in ('token.txt','.credentials.json') or q.suffix.lower() in ('.db','.sqlite','.sqlite3','.db-wal','.db-shm'):continue
   if q.suffix in ('.json','.jsonl','.stdout','.stderr','.png','.jpg'):
    copy(q,Path(label)/rel)
for q in (root/'decoder-probe-02').iterdir():
 if q.is_file() and q.suffix in ('.json','.png','.jpg','.webp'):copy(q,Path('decoder-probe')/q.name)
for q in (root/'codec-probe-02').iterdir():
 if q.is_file() and q.suffix=='.json':copy(q,Path('codec-probe')/q.name)
for name in ('agent_receipt_observe.py','check_installed_package_inputs.py','package_decoder_probe.py','review_package05_pins.py','inventory_installed_extras05.py','seal_agent_installed05.py'):
 copy(r/'_scratch'/name,Path('instruments')/name)
copy(r/'_scratch/installed_codec_probe05.py',Path('instruments/installed_codec_probe05.py'))
for name in (
 'agent_install_observer05.ps1','INSTALL-DESKTOP-OBSERVER-REPAIR-2026-09-09.md',
 'desktop-observer05.patch','desktop-observer05-source.json','ASTRA-DESKTOP-OBSERVER-VERDICT-2026-09-09.md',
 'validate_desktop_observer05.ps1','desktop-observer05-validation.json','desktop-observer05-validation-repair.json',
 'run_installed_decoders05.py','run_installed_decoders05_v2.py','run_installed_decoders05_v3.py',
 'repair_decoder_launcher05.py','decoder-launcher05-repair.json','INSTALLED-DECODER-STARTUP-REPAIR-2026-09-09.md',
 'agent_receipt_observe_p4_02.py','prepare_p4_observer02.py','p4-observer02-receipt.json',
 'P4-COLLECTION-INPUT-REPAIR-2026-09-10.md','repair_collection_input05.py','p4-collection-input-repair.json',
 'agent_receipt_observe_p4_collect03.py','run_installed_decoders.py','prepare_portable_decoder_observer.py',
 'portable-decoder-observer-review.json','review_installed05.py',
 'INSTALLED-SEAL-INPUT-REPAIR-2026-09-10.md','sealed-agent-installed05.log'):
 copy(r/'_scratch'/name,Path('instruments')/name)
for q in (r/'_scratch').glob('agent-*-05*.stdout-stderr.log'):copy(q,Path('outer-logs')/q.name)
for q in (r/'_scratch').glob('agent-*05-observer.stdout-stderr.log'):copy(q,Path('outer-logs')/q.name)
for name in ('result.json',):copy(r/'_scratch/package05-preinstall-review-01'/name,Path('preinstall-pins')/name)
copy(a.summary,Path('summary.json'))
def sha(q):
 with q.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
# Disposable tokens may be read only here to prevent their accidental export.
# No ordinary keyring, auth directory or live index is opened or enumerated.
tokens=[]
for q in [*(c22/'profiles').glob('*/token.txt'),p4/'token.txt',root/'p4/profile/token.txt']:
 if q.is_file():
  value=q.read_text(encoding='utf8').strip()
  if len(value)>=16:tokens.append(value.encode())
for q in out.rglob('*'):
 if q.is_file() and q.suffix not in ('.png','.jpg','.webp'):
  data=q.read_bytes();assert all(token not in data for token in tokens),'Disposable token in export: '+str(q.relative_to(out))
manifest={'algorithm':'sha256','scope':'Actual Inno install/reinstall with delegated same-account isolated app/profile. Raw C22/P4 statuses remain unchanged; independent review is summary.json. No database, token or client authentication store exported.','files':{q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':sha(q)} for q in sorted(out.rglob('*')) if q.is_file()}}
(out/'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8',newline='\n')
print(json.dumps({'payloads':len(manifest['files']),'summary':summary},indent=2))
