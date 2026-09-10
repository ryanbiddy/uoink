import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\cadfc013-476\gemini')
out=r/'docs/library/proof/ryan-ffmpeg-pin-repair-2026-09-09';out.mkdir(exist_ok=False)
for base,labels,section in ((w,['gemini-native-baseline-01','gemini-native-pin-repair-01','gemini-native-core-01','gemini-native-final-01','astra-native-pin-w1'],'worker'),(r,['astra-native-pin-c1'],'checkout')):
 for label in labels:
  for name in ('tests.log','tests.xml','results.json','guard/sitecustomize.py','guard/ig_paths.py'):
   source=base/'_scratch'/label/name;assert source.is_file(),source
   target=out/section/label/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
shutil.copyfile(r/'_scratch/gemini-native-pin-repair-2026-09-09.patch',out/'worker.patch')
shutil.copyfile(r/'_scratch/NATIVE-PIN-REPAIR-BRIEF-2026-09-09.md',out/'brief.md')
shutil.copyfile(Path(__file__),out/Path(__file__).name)
summary={'worker':'cadfc013-4769-4fd8-8e90-176939658598','base':'e6f520c0bf548ff7500cc879e0eb2bf1feb23825','integrator_head_before_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'independent_worker':{'passed':36,'seconds':4.09},'independent_checkout':{'passed':36,'seconds':3.10},'product_change':'build.ps1 exact LGPL FFmpeg pin and distinct versioned cache','test_edits':False,'native_qualification':'../ryan-native-guard-review-2026-09-09/SHA256.json','scope':'No Setup or current Python upgrade. Worker report contains stale input-count and media-failure explanations, corrected by integrator verdict.'}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8')
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(len(files))
