"""Prepare fresh full-tree instruments; no candidate run or build starts here."""
import ast,difflib,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch';rows=[]
def adapt(original,target,changes):
    before=(s/original).read_text(encoding='utf8');after=before
    for old,new in changes:
        assert after.count(old)==1,(original,old)
        after=after.replace(old,new)
    ast.parse(after)
    path=s/target;assert not path.exists(),path
    path.write_text(after,encoding='utf8',newline='\n')
    (s/(target+'.diff')).write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile=original,tofile=target)),encoding='utf8',newline='\n')
    rows.append({'before':original,'after':target,'before_sha256':hashlib.sha256((s/original).read_bytes()).hexdigest(),'after_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'executed':False})
adapt('run_partitioned_repaired_tree.py','run_partitioned_mirror_tree09.py',[
 ("command=base+['--label',label,*selectors,'--runxfail','-p','_scratch.partition_receipt_plugin']", "command=base+['--label',label,*selectors,'--runxfail','-p','_scratch.partition_receipt_plugin']\n if name=='main':\n  env['IG_MIRROR_STATE_RECEIPT_PATH']=str(out/'mirror-state.jsonl')\n  command+=['-p','_scratch.mirror_state_receipt_plugin']")])
adapt('run_complete_candidate_durable.py','run_complete_mirror_tree09_durable.py',[
 ("assert a.label==('durable-tree-preflight01' if a.self_test else 'ryan-final-partitioned-08')","assert a.label==('durable-tree09-preflight01' if a.self_test else 'ryan-final-partitioned-09')"),
 ("str(r/'_scratch/run_partitioned_repaired_tree.py')","str(r/'_scratch/run_partitioned_mirror_tree09.py')")])
(s/'mirror-tree09-instrument-preparation.json').write_text(json.dumps({'purpose':'Observe new combined mirror repair only after reviewed integration; no test/build executed','changes':rows},indent=2)+'\n',encoding='utf8')
print(json.dumps({'prepared':len(rows),'executed':False}))
