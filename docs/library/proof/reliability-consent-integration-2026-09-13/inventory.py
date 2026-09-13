"""Enumerate and hash narrowly named documentary inputs; no execution/imports."""
from collections import Counter
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[1]
SCRATCH=ROOT/'_scratch'
WORKER=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\0851b440-86a\grok')
sha=lambda raw:hashlib.sha256(raw).hexdigest()
entries={}
def add(member,source):
    assert member not in entries,member
    source=Path(source)
    raw=source.read_bytes()
    # Documentary files only; no runtime, model, database or opaque binary input.
    assert source.suffix.lower() in {'.py','.cjs','.js','.txt','.json','.jsonl','.log','.xml','.md','.patch','.ps1','.cfg'} or source.name=='.gitattributes',source
    raw.decode('utf-8-sig')
    if re.search(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',raw):
        raise RuntimeError('Private-key material found; stop before archive: '+member)
    entries[member]={'member':member,'source':str(source),'bytes':len(raw),'sha256':sha(raw)}
def tree(prefix,source):
    for path in sorted(Path(source).rglob('*')):
        if path.is_file():add(prefix+'/'+path.relative_to(source).as_posix(),path)

seals=[('instrument01','reliability-focused-instrument01',31,'a06eee5c9ecc0b550b91dba9a930d91adfcb8588cc8ab68cf0be24f6e8dc2362'),
    ('node02','reliability-focused-node02',36,'0f82a7df43e7587ebc42f7c1556c0cbdd950bf1d37a3aeec27c22895a53d0c8d'),
    ('node03','reliability-focused-node03',33,'1dfd0be4152016645d75b680e52d8ebb5b53034f0ec02806c5e097fb3070095f'),
    ('node04','reliability-focused-node04',35,'a20480f1f7b3f24311a2422848a99c02d83bb7c73c5a9d1b2a6f936c5320a09a')]
for label,directory,count,digest in seals:
    base=SCRATCH/directory
    raw=(base/'SHA256.json').read_bytes();assert sha(raw)==digest
    manifest=json.loads(raw);assert manifest['payload_count']==count
    for row in manifest['payloads']:
        member='preparation/'+label+'/'+row['file']
        add(member,base/row['file'])
        assert entries[member]['bytes']==row['bytes'] and entries[member]['sha256']==row['sha256']
    add('preparation/'+label+'/SHA256.json',base/'SHA256.json')

tree('original-worker',SCRATCH/'reliability-grok-original01')
for name in ['reliability-original-keyword-probe01.py',
    'reliability-original-keyword-probe01-observed-failure.json',
    'RELIABILITY-KEYWORD-PROBE-SETUP-REPAIR-2026-09-13.md',
    'reliability-original-keyword-probe02.py','reliability-original-keyword-probe02-outer.json',
    'reliability-original-keyword-probe02.stderr.log','reliability-original-keyword-probe02.stdout.log']:
    add('keyword-probes/'+name,SCRATCH/name)
tree('keyword-probes/probe02',SCRATCH/'reliability-original-keyword02')
add('root/ASTRA-RELIABILITY-FOCUSED-ADMISSION-2026-09-13.md',SCRATCH/'ASTRA-RELIABILITY-FOCUSED-ADMISSION-2026-09-13.md')
add('root/RELIABILITY-CONSENT-SETTINGS-REPAIR-BRIEF-2026-09-13.md',ROOT/'docs/library/RELIABILITY-CONSENT-SETTINGS-REPAIR-BRIEF-2026-09-13.md')
add('root/reliability-grok-final04.patch',SCRATCH/'reliability-grok-final04.patch')
add('root/CHECKOUT-EOL-TRANSPORT.json',SCRATCH/'reliability-focused-node04/CHECKOUT-EOL-TRANSPORT.json')

runs=[('rlw01','reliability-focused-node02','worker-rlw01','ROOT-ADMISSION.worker01.json',WORKER),
    ('rlw02','reliability-focused-node03','worker-rlw02','ROOT-ADMISSION.worker02.json',WORKER),
    ('rlw03','reliability-focused-node04','worker-rlw03','ROOT-ADMISSION.worker03.json',WORKER),
    ('rlw04','reliability-focused-node04','worker-rlw04','ROOT-ADMISSION.worker04.json',WORKER),
    ('rlc04','reliability-focused-node04','checkout-rlc04','ROOT-ADMISSION.checkout04.json',ROOT)]
for label,directory,run,admission,target in runs:
    base=SCRATCH/directory
    tree('runs/'+label+'/launcher',base/'runs'/run)
    add('runs/'+label+'/root-admission.json',base/admission)
    for phase in ['c'] if label=='rlw01' else ['c','t']:
        phase_path=target/'_scratch'/(label+phase)
        for relative in ['results.json','tests.log','tests.xml','guard/ig_paths.py','guard/sitecustomize.py']:
            add('runs/'+label+'/verifier-'+phase+'/'+relative,phase_path/relative)
        observer=target/'_scratch'/(label+phase+'-membership')
        for name in ['membership.json','reports.jsonl','session.json']:
            add('runs/'+label+'/membership-'+phase+'/'+name,observer/name)
for _,directory,_,_ in seals[1:]:
    tree('outer/'+directory,SCRATCH/directory/'outer-receipts')

admission=json.loads((SCRATCH/'reliability-focused-node04/ROOT-ADMISSION.worker04.json').read_text(encoding='utf-8'))
admitted=admission['targets']['worker']['reviewed_files']
report='docs/library/RELIABILITY-CONSENT-SETTINGS-WORKER-2026-09-13.md'
names=list(admitted)
if report not in names:names.append(report)
bindings=[]
for name in names:
    raw=(WORKER/name).read_bytes()
    if name in admitted:assert sha(raw)==admitted[name],name
    checkout=(ROOT/name).read_bytes();assert checkout==raw,name
    add('source/final/'+name,WORKER/name)
    bindings.append({'file':name,'worker':str(WORKER/name),'checkout':str(ROOT/name),
        'bytes':len(raw),'sha256':sha(raw),'identical_between_roots':True,
        'bound_in_worker_admission':name in admitted})
for value,name in [(bindings,'FINAL-ROOT-BINDINGS.json'),
    ({'created_utc':datetime.now(timezone.utc).isoformat(),'file_count':len(entries),
        'total_uncompressed_bytes':sum(row['bytes'] for row in entries.values()),
        'groups':dict(Counter(member.split('/')[0] for member in entries)),
        'entries':[entries[key] for key in sorted(entries)]},'INPUT-LIST.json')]:
    with (OUT/name).open('x',encoding='utf-8',newline='\n') as stream:
        stream.write(json.dumps(value,indent=2)+'\n')
print(json.dumps({'files':len(entries),'bytes':sum(row['bytes'] for row in entries.values()),
    'groups':dict(Counter(member.split('/')[0] for member in entries)),
    'all_preparation_seals_unchanged':True,'final_roots_identical':True}))
