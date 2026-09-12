"""Review the four original package-07 views against retained state and cleanup."""
from pathlib import Path
import datetime as dt,hashlib,json
root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 07')
read=lambda name:json.loads((root/name).read_text(encoding='utf8'))
outer=read('browser-observation.json')
assert outer['status']=='completed_pending_independent_review'
assert outer['source_bindings_after'] and outer['guard_absent_after']
assert outer['pth_before']==outer['pth_after']
browser=read('c22/evidence/browser-held-observation.json')
first=browser['before_observation']
changes={name:[key for key,value in first.items() if value!=browser[name].get(key)] for name in ('after_observation','after_stop')}
assert all(set(value)=={'label','utc'} for value in changes.values()),changes
stop=browser['stop']
assert stop['exit']==0 and stop['stopped'] and stop['port_freed'] and stop['pth_preserved']['matches_original']
ledger=first['ledger_summary']
assert ledger['standing_charge_count']==1 and ledger['publication_count']==0
assert len(ledger['starts'])==1 and ledger['starts'][0]['state']=='failed'
assert ledger['starts'][0]['release_or_failure_code']=='worker_lost'
source=ledger['subscriptions'][0]
assert source['consent_state']=='on' and source['revision']==1 and source['back_catalog_enrolled']==1
assert ledger['items'][0]['state']=='eligible' and ledger['items'][0]['actual_starts']==1
assert ledger['items'][0]['blocked_reason']=='worker_lost'
visual=read('c22/artifacts/browser-observation-complete.json')
assert len(visual['images'])==4 and not visual['browser_page_errors'] and visual['browser_close_exit']==0
for row in visual['images']:
    path=root/'c22/artifacts'/row['file']
    assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
    stamp=dt.datetime.fromisoformat(row['captured_file_mtime_utc'])
    assert dt.datetime.fromisoformat(browser['utc_start'])<=stamp<=dt.datetime.fromisoformat(browser['utc_end'])
summary={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'package_sha256':outer['package_sha256'],
    'source':outer['package_source'],'status':'passed_independent_visual_and_state_review',
    'images':4,'state_changes':changes,'visible':visual['reviewed_visible_fields'],
    'helper_stop_exit':stop['exit'],'owned_port_freed':True,'interpreter_and_guard_restored':True,
    'scope':'Same-account isolated installed dashboard only; original raw pending_review is retained.',
    'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
with (root/'browser07-independent-review.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
