"""Review retained installed observations without opening any database."""
import datetime as dt,hashlib,json
from pathlib import Path
r=Path(__file__).resolve().parents[1];root=Path(r'E:\AI\projects\uoink\installation-receipts\Agent Install 05')
def read(name):return json.loads((root/name).read_text(encoding='utf8'))
package=json.loads((r/'docs/library/proof/candidate-package-05-2026-09-09/package-manifest.json').read_text())
c22=read('c22-observation.json');assert c22['verdict']['counts']=={'pass':11,'fail':0,'unexecuted':3,'executed':11}
assert c22['source_bindings_after'] and c22['guard_absent_after'] and c22['pth_before']==c22['pth_after']
assert not c22['unexpected_runtime_errors'] and all(x['observed']=='dead' for x in c22['owned_command_liveness'])
comparison=read('installed-file-comparison.json');assert comparison['compared']==32054 and not comparison['failures']
for stage in ('install','same-version-reinstall'):
 row=read(stage+'.json');assert row['exit']==0 and row['package_sha256']==package['package_sha256']
b=read('c22/evidence/browser-held-observation.json');first=b['before_observation']
for key in ('after_observation','after_stop'):
 changed=[field for field,value in first.items() if value!=b[key].get(field)]
 assert set(changed)=={'label','utc'},changed
assert b['stop']['exit']==0 and b['stop']['stopped'] and b['stop']['port_freed'] and b['stop']['pth_preserved']['matches_original']
assert first['ledger_summary']['standing_charge_count']==1 and first['ledger_summary']['publication_count']==0
assert first['ledger_summary']['starts'][0]['release_or_failure_code']=='worker_lost'
for name in ('browser-library.jpg','browser-sources-summary.jpg','browser-sources-detail.jpg','browser-activity.jpg'):
 assert (root/'c22/artifacts'/name).read_bytes().startswith(b'\xff\xd8')
assert (root/'c22/artifacts/browser-checkpoint.png').read_bytes()==(root/'c22/artifacts/browser-sources-detail.jpg').read_bytes()
p4=read('p4-02/profile/collection.json');assert p4['counts']=={'passed':15,'failed':0,'blocked':0,'unobserved':8,'pending_review':0}
assert not p4['product_findings'] and not p4['isolation']['instrument_only']
stdio=read('p4-02/profile/stdio-check-original-installed.json')
assert stdio['installed_credit'] and not stdio['product_findings'] and not stdio['fake_child_used']
assert stdio['inspection']['packet_and_prompt_subset_complete'] and stdio['reconnect']['distinct']
assert stdio['unavailable_storage']['expected_refusal'] and not stdio['unavailable_storage']['replacement_index_created']
assert stdio['guard_restore']['children_confirmed_gone']
for stage in ('prepare','check','prepare-client','collect'):
 operator=read('p4-02/profile/operator-'+stage+'.json');assert operator['exit_code']==0 and operator['cleanup']['cleaned']
decoder=read('decoder-commands-02.json');assert decoder['status']=='passed' and decoder['startup_restored']
summary={
 'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'package_sha256':package['package_sha256'],'build_source':package['build_source'],
 'setup_observed':True,'same_version_reinstall_observed':True,'throwaway_account':False,'ordinary_installation_replaced':False,
 'account_scope':'Same non-elevated Windows account, separate app/data/credential namespace and uninstall/Start Menu entry. Not OS-wide containment.',
 'installed_files_compared':32054,'installed_files_failed':0,'setup_exits':[0,0],
 'desktop_observer':'Reviewed supplement skips redirected Desktop contents, records reparse metadata, and requires actual empty Tasks INF plus Inno no-desktop-task logs. Original pre-Setup refusal retained.',
 'c22_raw_counts':c22['verdict']['counts'],'c22_automated_scenarios':'11 passed, 0 failed; original three manual placeholders retained',
 'browser':{'status':'partial','images':4,'same_state_before_after_stop':True,'visible':'Standing consent on; enrollment 1/25, starts used 1/10, Activity has zero running/queued/completed-loaded items. Source detection health is healthy.','missing_visual_fields':['Consent revision appears only in persisted snapshot','Settled worker_lost reason is not shown in visible source/Activity rows'],'image_format':'Original JPEG. Legacy browser-checkpoint.png is byte-identical JPEG; no conversion.','cleanup':'owned helper exit zero, port freed and exact startup/guard restoration affirmed'},
 'p4_raw_counts':p4['counts'],'p4_route_installed_credit':stdio['installed_credit'],'p4_collection_installed_credit':p4['isolation']['installed_credit'],
 'p4_product_findings':p4['product_findings'],'p4_unobserved':[row['name'] for row in p4['checkpoints'] if row['status']=='unobserved'],
 'p4_notes':'Actual installed stdio route verified; overall collector keeps installed_credit false. Terminated transport/wrapper exit one is preserved, not a graceful-exit claim. Independent fixture checks used no real client.',
 'client':'Prepared fresh empty isolated configuration; no credentials copied/inspected, no model invoked. User-controlled sign-in and subscription/extra-usage verification remain required.',
 'decoders':'Installed image/crypto and product-loader WAV observations pass under temporarily disabled site import. Exact ._pth restored. This is instrumented compatibility evidence.',
 'failed_history':['Desktop observer pre-Setup reparse refusal','Decoder launcher SystemRoot key error before spawn','Decoder probe no_site assertion before imports','P4 prepare embedded import failure','P4 collect explicit operator input missing before child spawn'],
 'release_ready':False,'main_merged':False,'published':False,
 'open':['Real-client and visual everyday-flow receipts','Browser missing visible revision/recovery detail','Historical AT6 exit disposition','Retained dependency findings and unsigned package','Ryan main/public release decision'],
}
out=r/'_scratch/installed05-reviewed-summary.json'
with out.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(summary,indent=2)+'\n')
print(json.dumps({'setup':True,'c22':summary['c22_raw_counts'],'p4':summary['p4_raw_counts'],'browser':'partial','release_ready':False}))
