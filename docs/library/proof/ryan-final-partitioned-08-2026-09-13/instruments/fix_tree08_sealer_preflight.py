"""Correct an unused seal reader to the supervisor's actual terminal schema."""
from pathlib import Path
import ast, difflib, hashlib, json, shutil
s=Path(__file__).resolve().parent
p=s/'seal_partitioned_final_tree08.py'
before=p.read_text(encoding='utf8')
assert before.count("state['status']=='finished'")==1
after=before.replace("state['status']=='finished'", "state['status']=='child_exited'")
needle="for folder in ('ryan-final-partitioned-08-supervisor'"
assert needle in after
after=after.replace(needle,"assert state['aggregate_summary_present'] is True and state['aggregate_summary_sha256']==hashlib.sha256((raw/'summary.json').read_bytes()).hexdigest()\n"+needle)
after=after.replace("'rebind_package09_instruments13.py','run_combined_candidate13.py'", "'rebind_package09_instruments13.py','fix_tree08_sealer_preflight.py','tree08-sealer-preflight.json','run_combined_candidate13.py'")
ast.parse(after)
archive=s/'package09-unused-drafts-before-tree08'
shutil.copyfile(p,archive/'seal_partitioned_final_tree08-before-preflight.py')
(archive/'tree08-sealer-preflight.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True))),encoding='utf8')
p.write_text(after,encoding='utf8',newline='\n')
(s/'tree08-sealer-preflight.json').write_text(json.dumps({'reason':'Source review found the actual durable supervisor uses child_exited, not finished. Correct the unused reader before execution and require its exact aggregate-summary hash. No measurement or failed sealer run occurred.', 'before_sha256':hashlib.sha256(before.encode()).hexdigest(),'after_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed_sealer':False},indent=2)+'\n',encoding='utf8')
print('Unused sealer schema corrected; no observation executed.')
