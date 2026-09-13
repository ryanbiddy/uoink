import hashlib,json,subprocess,xml.etree.ElementTree as ET
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
base=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library')
worker=base / '6c96f0a3-c02/gemini'
first=base / 'db13e13b-ff8/gemini'
empty=base / '85ce8600-466/gemini'
out=root / 'docs/library/proof/runtime-graph-integrator-2026-09-12'
out.mkdir(exist_ok=False)
def put(name,data):
    p=out / name
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('xb') as stream: stream.write(data)
def copy(name,p): put(name,p.read_bytes())
def archive(name,directory):
    for p in sorted(directory.rglob('*')):
        if p.is_file(): copy(name+'/'+p.relative_to(directory).as_posix(),p)
verdict=root / 'docs/library/RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md'
raw=verdict.read_text(encoding='utf8')
raw=raw.replace('Accept the repaired offline checker, subject to checkout verification.','Accept the repaired offline checker after independent verification in both roots.')
raw=raw.replace('Checkout verification follows raw git\ndiff export and git apply --3way.',
                'Checkout verification passes the same 36 cases after raw git\ndiff export and git apply --3way (worker 7.70 s, checkout 6.52 s).')
verdict.write_text(raw,encoding='utf8',newline='\n')
archive('original-worker',worker / '_scratch/runtime-graph-original')
archive('repair-worker-before-astra',worker / '_scratch/graph-pre-astra')
counts={}
groups=[('original',first,['graph12-worker-original01']),
        ('worker',worker,['graph12-repaired-worker01','graph12-astra-worker01','graph12-astra-worker02','graph12-astra-worker03']),
        ('checkout',root,['graph13-checkout01']),
        ('negative',worker / '_scratch/graph-pre-astra-probes',['original01'])]
for label,tree,runs in groups:
    for name in runs:
        directory=tree / '_scratch' / name
        for p in directory.iterdir():
            if p.is_file():copy('runs/'+label+'/'+name+'/'+p.name,p)
        for p in (directory / 'guard').glob('*.py'):copy('runs/'+label+'/'+name+'/guard/'+p.name,p)
        counts[label+'/'+name]=[n.attrib for n in ET.parse(directory / 'tests.xml').getroot().iter('testsuite')]
for rel in ['scripts/check_runtime_graph.py','tests/test_runtime_graph_boundaries.py']:
    copy('negative-source/'+rel,worker / '_scratch/graph-pre-astra-probes' / rel)
for name in ['runtime-graph01-dispatch','runtime-graph02-dispatch','runtime-graph-boundary12-dispatch01','graph12-boundary-review02']:
    archive('dispatch-and-diagnostics/'+name,root / '_scratch' / name)
for name in ['worker.patch.gz','apply.stdout','apply.stderr','result.json']:
    copy('integration/'+name,root / '_scratch/graph13-integration01' / name)
for name in ['repair_graph13.py','finish_graph13.py','integrate_graph13.py','seal_graph13.py','run_media_verify12.py','integrator_verify.py']:
    copy('instruments/'+name,root / '_scratch' / name)
for rel in ['scripts/check_runtime_graph.py','tests/test_runtime_graph.py','tests/test_runtime_graph_boundaries.py',
            'docs/library/RUNTIME-GRAPH-01-2026-09-12.md','docs/library/RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md']:
    copy('source/'+rel,root / rel)
bindings={}
for name in ['runtime-graph-01-2026-09-12','runtime-graph-review-2026-09-12','runtime-graph-astra-review-2026-09-12']:
    directory=root / 'docs/library/proof' / name
    for p in sorted(directory.rglob('*')):
        if p.is_file():
            relative=p.relative_to(directory)
            assert p.read_bytes()==(worker / 'docs/library/proof' / name / relative).read_bytes()
            if name=='runtime-graph-01-2026-09-12':assert p.read_bytes()==(first / 'docs/library/proof' / name / relative).read_bytes()
            bindings[name+'/'+relative.as_posix()]=hashlib.sha256(p.read_bytes()).hexdigest()
put('capture-bindings.json',(json.dumps(bindings,indent=2)+'\n').encode())
put('review.json',(json.dumps({'base_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
 'counts_from_original_xml':counts,'retained_capture_files':len(bindings),
 'original_capture_payloads':306,'original_manifest_entries':304,
 'integration_patch_sha256':hashlib.sha256((root / '_scratch/graph13-integration01/worker.patch').read_bytes()).hexdigest(),
 'empty_worker':{'path':str(empty),'status':subprocess.check_output(['git','status','--porcelain'],cwd=empty,text=True),
 'required_files':{rel:(empty / rel).exists() for rel in ['scripts/check_runtime_graph.py','tests/test_runtime_graph.py',
 'docs/library/RUNTIME-GRAPH-BOUNDARY-REVIEW-2026-09-12.md','docs/library/proof/runtime-graph-01-2026-09-12']}},
 'production_pins_changed':False,'models_loaded':False,'release_ready':False},indent=2)+'\n').encode())
manifest={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
(out / 'SHA256.json').write_text(json.dumps(manifest,indent=2)+'\n',encoding='utf8')
print(json.dumps({'payloads':len(manifest),'capture_bindings':len(bindings),'runs':counts}))
