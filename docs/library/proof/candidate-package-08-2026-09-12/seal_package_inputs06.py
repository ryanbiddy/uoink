"""Capture real compiler inputs before receipt instrumentation touches staging."""
import argparse,datetime as dt,fnmatch,hashlib,json,re,shutil,stat,subprocess
from pathlib import Path
p=argparse.ArgumentParser()
p.add_argument('--source',required=True)
p.add_argument('--build-receipt',required=True,type=Path)
p.add_argument('--out',required=True,type=Path)
a=p.parse_args()
r=Path(__file__).resolve().parents[1];stage=r/'installer/staging'
def git(*args):return subprocess.check_output(['git',*args],cwd=r,text=True,encoding='utf8').strip()
def sha(path):
    with path.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def save(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf8',newline='\n')
observation_head=git('rev-parse','HEAD')
subprocess.run(['git','merge-base','--is-ancestor',a.source,observation_head],cwd=r,check=True)
documentary_changes=git('diff','--name-only',a.source,observation_head).splitlines()
assert set(documentary_changes).issubset({'THIRD-PARTY-NOTICES.md'}),documentary_changes
assert not git('status','--porcelain','--untracked-files=no')
receipt=json.loads(a.build_receipt.read_text(encoding='utf-8-sig'))
assert receipt['status']=='built; not installed' and receipt['candidate']==a.source
artifact=Path(receipt['artifact']['path'])
assert artifact.stat().st_size==receipt['artifact']['bytes'] and sha(artifact)==receipt['artifact']['sha256']
a.out.mkdir(parents=True,exist_ok=False)
tracked={}
for entry in subprocess.check_output(['git','ls-tree','-r','-z',a.source],cwd=r).split(b'\0'):
    if entry:
        meta,name=entry.split(b'\t',1);mode,kind,blob=meta.decode().split()
        if kind=='blob':tracked[name.decode('utf8')]=blob
inventory=[];bindings=[];unmapped=[]
inno=(r/'installer/uoink.iss').read_text(encoding='utf8')
sources=[x.replace('\\','/') for x in re.findall(r'^Source: "staging\\([^"]+)"',inno,re.M)]
file_rules=[]
for source,tail in re.findall(r'^Source: "staging\\([^"]+)";(.*)$',inno,re.M):
 source=source.replace('\\','/')
 flags=re.search(r'Flags: ([^;]+)',tail)
 flags=flags.group(1).split() if flags else []
 dest=re.search(r'DestDir: "([^"]+)"',tail)
 assert 'DestName:' not in tail, 'Explicit rename mapping needed'
 file_rules.append({'source':source,'dontcopy':'dontcopy' in flags,'destination':dest.group(1).replace('\\','/') if dest else None})
assert [row['source'] for row in file_rules if row['dontcopy']]==['upgrade_prep.ps1']
wizard_resources=set()
for value in re.findall(r'^Wizard(?:Small)?ImageFile=(.+)$',inno,re.M):
 for item in value.strip().split(','):
  assert item.startswith('staging\\')
  wizard_resources.add(item.removeprefix('staging\\').replace('\\','/'))
assert len(wizard_resources)==8

def layout(relative):
 matches=[rule for rule in file_rules if fnmatch.fnmatchcase(relative,rule['source'])]
 if relative in wizard_resources:
  assert not matches
  return {'install_role':'compiler-resource','reason':'Wizard bitmap embedded into Setup; no Files destination'}
 assert len(matches)==1,(relative,matches)
 rule=matches[0]
 if rule['dontcopy']:
  assert relative=='upgrade_prep.ps1' and rule['destination'] is None
  return {'install_role':'installer-only','reason':'Inno dontcopy; isolated PrepareToInstall skips the ordinary upgrade script','inno_source_pattern':rule['source']}
 assert rule['destination'] and rule['destination'].startswith('{app}')
 prefix=rule['source'].split('*',1)[0]
 suffix=relative[len(prefix):] if '*' in rule['source'] else Path(relative).name
 installed=rule['destination'].removeprefix('{app}').strip('/')
 installed=(installed+'/' if installed else '')+suffix
 assert installed==relative,(relative,installed)
 return {'install_role':'installed','installed_path':installed,'inno_source_pattern':rule['source']}

excluded=('server.log','token.txt')
assert not any(fnmatch.fnmatchcase(x,pattern) for x in excluded for pattern in sources)
for q in sorted(stage.rglob('*')):
    assert not q.lstat().st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,q
    if not q.is_file():continue
    relative=q.relative_to(stage).as_posix()
    if relative in excluded:continue
    digest=sha(q);placement=layout(relative);inventory.append({'path':relative,'bytes':q.stat().st_size,'sha256':digest,**placement})
    source=relative
    if relative in ('verify_install.ps1','upgrade_prep.ps1'):source='installer/'+relative
    elif relative in ('stop-server.bat','stop-server.ps1'):source='installer/templates/'+relative
    if source in tracked:
        assert sha(r/source)==digest,(relative,source)
        bindings.append({'staged_path':relative,'source_path':source,'source_git_blob':tracked[source],'checkout_and_staged_sha256':digest,'install_role':placement['install_role']})
    elif not relative.startswith(('python/','bin/','installer-assets/')) and relative not in ('VERSION','uoink.ico'):unmapped.append(relative)
assert not unmapped,unmapped
required=('index.py','uoink_install_isolation.py','server.py','uoink_mcp.py','library_work.py','source_subscriptions.py','library_mirror.py','library_mirror_vault_io.py','library_analysis.py','library_media.py','scripts/recall_hook.py')
assert all(any(x['staged_path']==name for x in bindings) for name in required)
assert not any(x['path'].endswith(('.pyc','.db','.db-wal','.db-shm','.sqlite','.sqlite3')) or Path(x['path']).name in ('token.txt','.credentials.json') for x in inventory)
assert len(bindings)==142
assert [(row['staged_path'],row['source_path']) for row in bindings if row['install_role']!='installed']==[('upgrade_prep.ps1','installer/upgrade_prep.ps1')]
shutil.copyfile(r/'installer/uoink.iss',a.out/'installer-definition.iss')
save(a.out/'staged-inventory.json',{'build_source':a.source,'scope':'Compiler inputs, before runtime instrumentation; not an extraction of installer bytes','files':inventory})
save(a.out/'source-bindings.json',{'build_source':a.source,'files':bindings})
save(a.out/'post-build-review.json',{'build_source':a.source,'observation_head':observation_head,'changed_paths':documentary_changes,'reason':'Only generated third-party notices were reviewed after compilation. Notices are not an Inno Files input or compiler resource. All staged source bindings still match the build-source blobs and current checkout bytes.'})
save(a.out/'package-manifest.json',{'installer_source_sha':a.source,'build_source':a.source,'package_sha256':sha(artifact),'package_bytes':artifact.stat().st_size,'package_name':artifact.name,'files':bindings,'installed':False,'published':False,'created_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'inno_definition_sha256':sha(r/'installer/uoink.iss'),'runtime_sha256':sha(stage/'python/python.exe')})
shutil.copyfile(a.build_receipt,a.out/'build-receipt.json')
shutil.copyfile(a.build_receipt.parent/'build.log',a.out/'build.log')
shutil.copyfile(Path(__file__),a.out/Path(__file__).name)
print(json.dumps({'source':a.source,'files':len(inventory),'bindings':len(bindings),'artifact':receipt['artifact'],'output':str(a.out)},indent=2))
