"""Build a portable receipt bundle from reviewed committed inputs; never install."""
import argparse,datetime as dt,hashlib,json,re,shutil,subprocess,urllib.parse,zipfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--validation-source',required=True);p.add_argument('--validation-proof',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
r=Path(__file__).resolve().parents[1]
def git(*args):return subprocess.check_output(['git',*args],cwd=r,text=True,encoding='utf8').strip()
def sha(path):
 with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
assert re.fullmatch('[0-9a-f]{40}',a.source) and re.fullmatch('[0-9a-f]{40}',a.validation_source)
assert git('rev-parse','HEAD')==a.source and not git('status','--porcelain','--untracked-files=no')
subprocess.run(['git','merge-base','--is-ancestor',a.validation_source,a.source],cwd=r,check=True)
subprocess.run(['git','diff','--exit-code',a.validation_source,a.source,'--','scripts/install_receipt','migrations','tests'],cwd=r,check=True,stdout=subprocess.DEVNULL)
tracked=set(git('ls-tree','-r','--name-only',a.source).splitlines())
proof_root=r/'docs/library/proof/candidate-package-03-2026-09-09'
package=json.loads((proof_root/'package-manifest.json').read_text())
artifact=r/'build'/package['package_name'];assert sha(artifact)==package['package_sha256'] and artifact.stat().st_size==package['package_bytes']
for row in package['files']:
 assert sha(r/row['source_path'])==row['checkout_and_staged_sha256'],row
 assert git('rev-parse',a.validation_source+':'+row['source_path'])==git('rev-parse',a.source+':'+row['source_path']),row
runbook=r/'docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md'
assert package['package_sha256'] in runbook.read_text(encoding='utf8'),'Runbook must bind the current package'
assert 'blocked before installation with the current package' not in runbook.read_text(encoding='utf8'),'Old runbook cannot ship'
required=['scripts/install_receipt/browser_checkpoint.py','scripts/install_receipt/receipt_integrity.py','scripts/install_receipt/p4_operator.py','scripts/install_receipt/cli.py','scripts/install_receipt/runner.py','scripts/install_receipt/scenarios.py','scripts/install_receipt/p4_prepare_fixture.py','scripts/install_receipt/p4_prepare_client.py','scripts/install_receipt/p4_stdio_check.py','scripts/install_receipt/p4_collect_evidence.py','scripts/install_receipt/p4_session.py']
assert all(name in tracked for name in required),'Both reviewed kits must be committed'
validation_rel='docs/library/proof/'+a.validation_proof
assert validation_rel+'/SHA256.json' in tracked
validation=json.loads((r/validation_rel/'SHA256.json').read_text())
for name,row in validation['files'].items():
 assert sha(r/validation_rel/name)==row['sha256'] and (r/validation_rel/name).stat().st_size==row['bytes']
selected={name for name in tracked if name.startswith('scripts/install_receipt/') or (name.startswith('migrations/') and name.endswith('.sql')) or (name.startswith('docs/library/') and '/proof/' not in name and name.endswith('.md')) or name.startswith(validation_rel+'/')}
active_proofs = ('candidate-package-03-2026-09-09', 'ryan-c22-bundled-02-2026-09-09',
 'ryan-p4-bundled-03-2026-09-09', 'ryan-startup-backfill-integration-2026-09-09',
 'ryan-c22-bundled-compatibility-2026-09-09', 'ryan-c22-version-query-2026-09-09',
 'ryan-package03-binding-2026-09-09', 'ryan-portable-operator-2026-09-09')
selected.update(n for n in tracked if any(n.startswith('docs/library/proof/'+proof+'/') for proof in active_proofs))
# Include tracked local Markdown link targets. Never follow external links or read untracked/private data.
pending=[name for name in selected if name.endswith('.md')];seen=set();excluded=[]
while pending:
 name=pending.pop()
 if name in seen:continue
 seen.add(name)
 for target in re.findall(r'\]\(([^\n)]+)\)',(r/name).read_text(encoding='utf8')):
  target=target.strip().split(' "',1)[0].strip('<>');target=urllib.parse.unquote(target.split('#',1)[0])
  if not target or re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*:',target) or target.startswith('/') :continue
  q=((r/name).parent/target).resolve()
  if not q.is_relative_to(r):continue
  rel=q.relative_to(r).as_posix()
  if rel in tracked:
   if Path(rel).suffix.lower() in ('.db','.sqlite','.sqlite3') or Path(rel).name.lower() in ('token.txt','.credentials.json'):
    excluded.append({'referrer':name,'target':rel,'reason':'private historical data stays in the retained source archive'});continue
   selected.add(rel)
   if rel.endswith('.md'):pending.append(rel)
assert not any(Path(name).suffix.lower() in ('.db','.sqlite','.sqlite3') or Path(name).name.lower() in ('token.txt','.credentials.json') for name in selected)
out=a.out.resolve();assert out.is_relative_to(r/'_scratch') or out.is_relative_to(r/'build')
out.mkdir(parents=True,exist_ok=False)
for name in sorted(selected):
 dest=out/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(r/name,dest)
shutil.copyfile(artifact,out/artifact.name)
shutil.copyfile(proof_root/'source-bindings.json',out/'source-bindings.json')
manifest=dict(package,candidate_sha=a.validation_source,validation_source=a.validation_source,bundle_source=a.source,sealed_by='Astra',expected_package_sha256=package['package_sha256'])
example=json.loads((r/'scripts/install_receipt/c22_operator_manifest.example.json').read_text(encoding='utf8'))
for key,value in example.items():manifest.setdefault(key,value)
save(out/'package-manifest.json',manifest);save(out/'c22-operator-manifest.json',manifest)
save(out/'historical-data-omissions.json',excluded)
save(out/'release-state.json',{'bundle_source':a.source,'validation_source':a.validation_source,'build_source':package['build_source'],'package_sha256':package['package_sha256'],'installed':False,'published':False,'main_merged':False,'receipt_scope':'Ryan-owned isolated install, followed by independent C22/P4 review','librarian_apply_enabled':False,'phase5_part_b':'deferred','speaker_attribution':'not claimed'})
(out/'START-HERE.md').write_text('''# Living Library candidate receipt bundle

Start with [Ryan\'s installation runbook](docs/library/INSTALL-RECEIPT-RUNBOOK-2026-09-09.md).
Use one throwaway Windows profile and the exact recorded commands. Retain failed
and incomplete evidence. Installation does not itself approve the release.

[Release notes](docs/library/RELEASE-NOTES-LIVING-LIBRARY.md) explain all phases,
measured results and remaining decisions. Other reports are historical records.
The complete source and proof history is backed up on the authorized branch;
the bundle contains the receipt tools, required migrations and linked notes.

No label application, paid API, new source fetch or speaker-attribution claim.
Do not use the ordinary library profile or port 5179. No main merge is included.
''',encoding='utf8',newline='\n')
files={x.relative_to(out).as_posix():{'bytes':x.stat().st_size,'sha256':sha(x)} for x in sorted(out.rglob('*')) if x.is_file()}
save(out/'BUNDLE-SHA256.json',{'bundle_source':a.source,'validation_source':a.validation_source,'files':files})
zip_path=out.with_suffix('.zip');assert not zip_path.exists()
stamp=dt.datetime.fromtimestamp(int(git('show','-s','--format=%ct',a.source)),dt.timezone.utc).timetuple()[:6]
with zipfile.ZipFile(zip_path,'x',allowZip64=True) as archive:
 for x in sorted(out.rglob('*')):
  if not x.is_file():continue
  info=zipfile.ZipInfo(x.relative_to(out).as_posix(),date_time=stamp)
  info.compress_type=zipfile.ZIP_STORED if x.suffix.lower()=='.exe' else zipfile.ZIP_DEFLATED
  with x.open('rb') as src,archive.open(info,'w',force_zip64=True) as dest:shutil.copyfileobj(src,dest,1024*1024)
with zipfile.ZipFile(zip_path) as archive:
 assert set(archive.namelist()) == set(files) | {'BUNDLE-SHA256.json'}
 assert archive.testzip() is None
 assert hashlib.sha256(archive.read('BUNDLE-SHA256.json')).hexdigest()==sha(out/'BUNDLE-SHA256.json')
 for name,row in files.items():
  with archive.open(name) as f:assert hashlib.file_digest(f,'sha256').hexdigest()==row['sha256'],name
save(out.with_suffix('.receipt.json'),{'bundle_source':a.source,'validation_source':a.validation_source,'build_source':package['build_source'],'path':str(zip_path),'bytes':zip_path.stat().st_size,'sha256':sha(zip_path),'manifest_sha256':sha(out/'BUNDLE-SHA256.json'),'payload_files':len(files),'all_zip_member_hashes_verified':True,'installed':False,'published':False})
print(out.with_suffix('.receipt.json').read_text())
