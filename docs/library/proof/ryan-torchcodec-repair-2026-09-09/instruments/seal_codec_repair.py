import hashlib,json,shutil,subprocess
from pathlib import Path
r=Path(__file__).resolve().parents[1];w=r.parent/'Yoink-library-codec-repair'
out=r/'docs/library/proof/ryan-torchcodec-repair-2026-09-09';out.mkdir(parents=True,exist_ok=False)
def copy(source,relative):
 target=out/relative;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
for base,label in [(w/'_scratch/astra-codec-w1','worker'),(r/'_scratch/astra-codec-c1','checkout'),(r/'_scratch/native-binary-candidates-04','native-metadata'),(r/'_scratch/native-scan-shared-04','scan')]:
 for source in base.rglob('*'):
  if source.is_file() and source.suffix.lower() in ('.json','.log','.txt','.stdout','.stderr','.sha256'):copy(source,Path(label)/source.relative_to(base))
for relative in ('codec-integrator.patch','read_active_codec_run.py','run_codec_verification.py','prepare_product_codec_probe.py','probe_torchcodec_product.py','probe_torchcodec_shared.py','run_product_codec_probe.ps1','fetch_ffmpeg_shared_candidate.py','prepare_torchcodec_dlls.py','package04-preservation.json','seal_codec_repair.py'):
 copy(r/'_scratch'/relative,Path('instruments')/relative)
for source,relative in [(r/'_scratch/torchcodec-native-01/receipt.json','native-dlls.json'),(r/'_scratch/torchcodec-shared-probe-01/result.json','diagnostic-probe.json'),(r/'_scratch/torchcodec-product-probe-01/result/result.json','product-probe.json'),(r/'_scratch/torchcodec-product-probe-01/source-binding.json','product-source-binding.json'),(r/'docs/library/TORCHCODEC-INTEGRATOR-SUPPLEMENT-2026-09-09.md','brief.md')]:copy(source,relative)
(out/'gemini-failed-run.txt').write_bytes(subprocess.check_output([r'C:\Python314\python.exe','-I','-S','-B',str(r/'_scratch/read_active_codec_run.py')],cwd=r))
files={q.relative_to(out).as_posix():{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(out.rglob('*')) if q.is_file()}
(out/'SHA256.json').write_text(json.dumps({'algorithm':'sha256','files':files},indent=2)+'\n',encoding='utf8')
print(json.dumps({'proof':str(out),'payloads':len(files)},indent=2))
