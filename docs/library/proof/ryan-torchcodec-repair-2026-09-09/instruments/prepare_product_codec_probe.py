import hashlib,json,shutil
from pathlib import Path
r=Path(__file__).resolve().parents[1]
out=r/'_scratch/torchcodec-product-probe-01';out.mkdir(exist_ok=False)
app=out/'app';native=app/'bin/torchcodec';native.mkdir(parents=True)
rows=json.loads((r/'_scratch/torchcodec-native-01/receipt.json').read_text(encoding='utf8'))['files']
for row in rows:
 source=Path(row['path'])
 with source.open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
 shutil.copyfile(source,native/source.name)
shutil.copyfile(r/'whisper_runner.py',app/'whisper_runner.py')
code=(r/'_scratch/probe_torchcodec_shared.py').read_text(encoding='utf8')
code=code.replace("out=r/'_scratch/torchcodec-shared-probe-01'","out=r/'_scratch/torchcodec-product-probe-01/result'")
code=code.replace("handle=os.add_dll_directory(str(dlls))", "app=r/'_scratch/torchcodec-product-probe-01/app'\nsys.path.insert(0,str(app))\nimport whisper_runner\nassert whisper_runner._PACKAGED_DECODER_DLL_HANDLE is not None\nhandle=whisper_runner._PACKAGED_DECODER_DLL_HANDLE\ndlls=app/'bin/torchcodec'")
(r/'_scratch/probe_torchcodec_product.py').write_text(code,encoding='utf8')
archive=Path(json.loads((r/'_scratch/native-scan-shared-04/scan.json').read_text(encoding='utf-8-sig'))['file'])
cache=r/'build/cache/ffmpeg-n7.1.5-win64-lgpl-shared.zip'
assert not cache.exists()
shutil.copyfile(archive,cache)
(out/'source-binding.json').write_text(json.dumps({'source':'whisper_runner.py','sha256':hashlib.sha256((app/'whisper_runner.py').read_bytes()).hexdigest(),'dlls':rows},indent=2)+'\n',encoding='utf8')
