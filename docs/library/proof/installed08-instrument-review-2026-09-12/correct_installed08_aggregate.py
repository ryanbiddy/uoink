"""Replace stale prior-run prose with current evidence fields before execution."""
import ast,difflib,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1];s=r/'_scratch';p=s/'review_installed08.py';old=p.read_text(encoding='utf8');new=old
new=new.replace("browser=read('browser07-independent-review.json')","browser=read('browser08-independent-review.json')")
needle="assert published['status']=='passed_bounded_installed_publication_and_export'\n"
assert new.count(needle)==1
new=new.replace(needle,needle+'''recall=clients['recall_observations']
assert len(recall)==1 and recall[0]['exit_code']==0 and not recall[0]['timed_out']
assert recall[0]['output_utf8']=='' and recall[0]['stderr_utf8']==''
tool_calls=native['total_p4_tool_calls']+published['actual_tool_calls']
successes=native['hook_events'].get('PostToolUse',0)+published['hook_events'].get('PostToolUse',0)
failures=native['hook_events'].get('PostToolUseFailure',0)+published['hook_events'].get('PostToolUseFailure',0)
assert tool_calls==successes and failures==0
sentinel_requests=native['sentinel_requests']+published['sentinel_requests']
assert native['sentinel_calls']==published['sentinel_calls']==0
''')
new=new.replace("'actual_client_tool_calls':44,'successful_terminal_hooks':44,'failed_terminal_hooks':0,","'actual_client_tool_calls':tool_calls,'successful_terminal_hooks':successes,'failed_terminal_hooks':failures,")
new=new.replace("'sentinel_discovery_requests':15,","'sentinel_discovery_requests':sentinel_requests,")
needle="'recall':'Hook exits zero with empty output in 93.5668 ms. Negative silence only; no positive injected retrieval credit.',"
assert needle in new
new=new.replace(needle,"'recall':{'exit_code':recall[0]['exit_code'],'elapsed_ms':recall[0]['elapsed_ms'],'output_empty':True,'positive_injection_credit':False,'replacement_index_created':recall[0]['replacement_index_created']},")
new=new.replace("'Native-client citation/brief/chapter GUI interactions and positive Recall injection remain unobserved; no native UI automation surface is available in this session.'","'Desktop-client citation/brief/chapter GUI interactions and positive Recall injection remain unobserved. Native Uoink dashboard observation is reviewed separately; the invalid Desktop profile override is blocked.'")
new=new.replace("'history':'All old partials and two package-06 failed exports retained. One new independent-review glob error retained with the unchanged observation records and corrected reader.'","'history':'Prior failed/partial measurements remain unchanged. This aggregate derives timings and action counts from the new package-08 receipts; it does not copy prior outcomes.'")
ast.parse(new);(s/'review_installed08.py.initial-draft.txt').write_bytes(p.read_bytes())
p.write_text(new,encoding='utf8',newline='\n')
(s/'review_installed08.py.preexecution.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='unexecuted-prior-label-adapter',tofile='current-evidence-aggregate')),encoding='utf8')
(s/'installed08-aggregate-preexecution-review.json').write_text(json.dumps({'reason':'Prior-run label adapter still named browser07 and copied old recall timing, hook counts and native-unavailable prose. Bind current review and derive actual counts/timing. Preserve all success, exact comparison and cleanup assertions. No observation has run.','sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'executed':False},indent=2)+'\n',encoding='utf8')
print('Current-evidence aggregate prepared; no prior timing or native availability claim copied.')
