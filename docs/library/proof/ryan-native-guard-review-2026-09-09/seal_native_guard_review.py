"""Archive observed diagnostics and native provenance without rewriting outcomes."""
import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\e0082e87-00e\gemini')
out=r/'docs/library/proof/ryan-native-guard-review-2026-09-09';out.mkdir(exist_ok=False)
def cp(source,name):
 target=out/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for root,labels,section in ((w,['gemini-diag-standalone-media','gemini-diag-p4-then-media','gemini-diag-standalone-long','gemini-diag-p4-then-long','gemini-diag-wrapper','gemini-diag-wrapper2','astra-guard-diag-w1','astra-media-gpl-w1'],'worker'),(r,['astra-guard-diag-c1','astra-media-gpl-c1','astra-shipping-media-c1','astra-shipping-media-c2'],'checkout')):
 for label in labels:
  run=root/'_scratch'/label
  assert run.is_dir(),run
  for name in ('tests.log','tests.xml','results.json','original_probe.py'):
   if (run/name).is_file():cp(run/name,f'{section}/{label}/{name}')
  for name in ('sitecustomize.py','ig_paths.py'):
   if (run/'guard'/name).is_file():cp(run/'guard'/name,f'{section}/{label}/guard/{name}')
  for q in (root/'_scratch'/(label+'-0')).rglob('native-observation.json'):
   cp(q,f'{section}/{label}/'+q.relative_to(root/'_scratch'/(label+'-0')).as_posix())
for name in ('native-binary-candidates-01','native-binary-candidates-02','native-scan-gpl-01','native-scan-lgpl-02','native-bin-gpl-01','native-bin-lgpl-02','native-release-metadata-01'):
 for q in sorted((r/'_scratch'/name).iterdir()):
  if q.is_file() and q.suffix not in ('.zip','.exe'):
   cp(q,'native/'+name+'/'+q.name)
for name in ('P4-GUARD-DIAGNOSTIC-BRIEF-2026-09-09.md','NATIVE-PIN-REPAIR-BRIEF-2026-09-09.md','PYTHON-313-QUALIFICATION-BRIEF-2026-09-09.md','SHIPPING-PROBE-REPAIR-2026-09-09.md','gemini-native-security-review-2026-09-09.patch','gemini-p4-guard-diagnostic-2026-09-09.patch','integrator_verify.py','fetch_native_release_metadata.py','fetch_ffmpeg_candidates.py','fetch_ffmpeg_monthly.py','scan_native_archive.ps1','prepare_verified_ffmpeg.py','test_native_shipping_probe.py'):
 cp(r/'_scratch'/name,'instruments/'+name)
cp(Path(__file__),'seal_native_guard_review.py')
source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip()
summary={'source':source,'diagnostic_worker':'e0082e87-00e4-4c77-9cb4-b1d03485f036','native_review_worker':'a8752e4f-c54','product_or_test_edits':False,'independent_guard_worker':{'passed':1,'failed':1,'seconds':1.93},'independent_guard_checkout':{'passed':1,'failed':1,'seconds':1.57},'original_media_gpl_worker':{'passed':2,'seconds':2.86},'original_media_gpl_checkout':{'passed':2,'seconds':2.24},'shipping_lgpl_first_probe':{'passed':3,'failed':1,'seconds':3.03},'shipping_lgpl_corrected_probe':{'passed':4,'failed':0,'seconds':2.68},'scope':'Synthetic media only. Rejected parent-guard deletion. Final complete partitioned tree still pending. GPL remains private test-only. No Setup, live-index, 5179, model, diarization or credential execution.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'files':len(files),'summary':summary},indent=2))
