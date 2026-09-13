"""Bind unused package observers to the durable full-tree source; execute nothing."""
from pathlib import Path
import ast, difflib, hashlib, json, shutil
r=Path(__file__).resolve().parents[1]
s=r/'_scratch'
old='e53fe0e52131d7b210484b7c89850d1bcb31b9ee'
new='9dd0cfbb8390290f85a19529a22e4f0dedc0d0af'
archive=s/'package09-unused-drafts-before-tree08'
archive.mkdir(exist_ok=False)
rows=[]
def change(name, after, target=None):
    src=s/name; dest=s/(target or name)
    before=src.read_text(encoding='utf8')
    assert after!=before
    shutil.copyfile(src,archive/name)
    ast.parse(after)
    dest.write_text(after,encoding='utf8',newline='\n')
    delta=''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=name,tofile=dest.name))
    (archive/(dest.name+'.diff')).write_text(delta,encoding='utf8',newline='\n')
    rows.append({'before':name,'after':dest.name,'before_sha256':hashlib.sha256((archive/name).read_bytes()).hexdigest(),
                 'after_sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'executed':False})
for name in ('run_installed_client09.py','observe_published_chapter09.py'):
    before=(s/name).read_text(encoding='utf8')
    assert before.count(old)==1
    change(name,before.replace(old,new))
name='seal_partitioned_final_tree07.py'
text=(s/name).read_text(encoding='utf8')
text=text.replace('ryan-final-partitioned-07-2026-09-13','ryan-final-partitioned-08-2026-09-13')
text=text.replace("'seal_partitioned_final_tree07.py','run_combined_candidate13.py'", "'seal_partitioned_final_tree08.py','run_complete_candidate_durable.py','rebind_package09_instruments13.py','run_combined_candidate13.py'")
needle="for filename in ('membership.json','session.json'):"
assert text.count(needle)==1
text=text.replace(needle,"""supervisor=r/'_scratch/ryan-final-partitioned-08-supervisor'
state=json.loads((supervisor/'state.json').read_text(encoding='utf8'))
assert state['source']==summary['source'] and state['status']=='finished' and state['child_exit'] in (0,1), state
for folder in ('ryan-final-partitioned-08-supervisor','ryan-final-partitioned-08-launch','durable-tree-preflight01-supervisor','package09-unused-drafts-before-tree08'):
 for src in (r/'_scratch'/folder).rglob('*'):
  if src.is_file():copy(src,Path('durable-observer')/folder/src.relative_to(r/'_scratch'/folder))
"""+needle)
change(name,text,'seal_partitioned_final_tree08.py')
name='finalize_package09.py'
text=(s/name).read_text(encoding='utf8')
needle="inventory=json.loads((out/'staged-inventory.json').read_text())['files']"
assert text.count(needle)==1
text=text.replace(needle,"""# Actual current-build signing status, never a reconstructed older receipt.
current=r/'build/Uoink-Setup-3.8.0.exe.signature.json'
signing=json.loads(current.read_text(encoding='utf8'))
assert signing['status']=='unsigned' and signing['signature_verified'] is False and signing['release_ready'] is False
assert signing['sha256']==obs['package_sha256'] and signing['details']['sha256']==obs['package_sha256']
attempt=Path(signing['attempt_directory']).resolve(strict=True)
assert attempt.parent==(r/'build/signing-attempts').resolve()
assert not attempt.is_symlink()
shutil.copyfile(current,out/'installer-signature.json')
for name in ('pending.json','unsigned.json'):
 src=attempt/name
 record=json.loads(src.read_text(encoding='utf8'))
 assert record['status']==name.removesuffix('.json') and record['attempt_directory']==signing['attempt_directory']
 target=out/'signing-attempt'/name;target.parent.mkdir(exist_ok=True)
 shutil.copyfile(src,target)
old=attempt/'previous.exe'
assert sha(old)=='69a5394d842dc7fb5ac770d65954894231b03533bc99db922f34793f372fd06c'
save(out/'signing-attempt/previous-installer-preservation.json',{'sha256':sha(old),'bytes':old.stat().st_size,'path':str(old),'same_as_package08':True})
for folder in ('package09-unused-drafts-before-tree08',):
 for src in (r/'_scratch'/folder).rglob('*'):
  if src.is_file():
   target=out/'observer-preparation'/folder/src.relative_to(r/'_scratch'/folder)
   target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,target)
for name in ('rebind_package09_instruments13.py','package09-tree08-binding.json','package09-tree08-binding-review.md','prepare_package09_instruments02.py','repair_package09_preparation.py'):
 shutil.copyfile(r/'_scratch'/name,out/name)
"""+needle)
change(name,text)
(s/'package09-tree08-binding.json').write_text(json.dumps({'source':new,'qualification_label':'ryan-final-partitioned-08','changes':rows,'build_executed':False,'installation_executed':False},indent=2)+'\n',encoding='utf8')
(s/'package09-tree08-binding-review.md').write_text('''# Package 09 observer binding, September 13

The first full-tree attempt was interrupted. Its frozen source e53fe0e is the
production parent of documentary 9dd0cfb. The fresh complete observation is
tree08. Two unused actual-client observers now require 9dd0cfb; original drafts
and exact diffs are retained. No fixture or behavioral assertion changes.

The fresh tree sealer compares the same 147 added cases to the last complete
2582-case tree06 and preserves the original aggregate. It also requires the
durable supervisor's actual terminal child exit and archives its launch/state.
The package finalizer now archives the real unsigned build/signing attempt,
checks its package hash, and verifies the retained previous installer. It does
not assert a successful signature or remove the existing security gate.

All edited Python observers parse. No build, installed observation, client,
model or new measurement ran during this preparation. Current source remains
frozen until tree08 terminates. Old attempts and package08 remain unchanged.

Ryan's later September 13 clarification pauses website and marketing work until
Astra and the council find the product ready for market. Local site drafts stay
saved; its browser session and preview server are closed. No website council run,
deployment or marketing action started. Complete product qualification first.
''',encoding='utf8',newline='\n')
print(json.dumps({'rebound':len(rows),'source':new,'executed_product':False}))
