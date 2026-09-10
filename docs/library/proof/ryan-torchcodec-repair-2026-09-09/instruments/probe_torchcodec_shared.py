"""Verify a candidate DLL repair with real generated-WAV decoding, without models."""
import hashlib,json,os,sys,wave
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/torchcodec-shared-probe-01';out.mkdir(exist_ok=False)
events=[]
def audit(event,args):
 if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo','subprocess.Popen'):
  events.append({'event':event,'refused':True});raise PermissionError('Native codec probe: network/subprocess refused')
 if event in ('open','sqlite3.connect') and args and isinstance(args[0],(str,bytes,os.PathLike)) and 'c:/users/hello/appdata/local/uoink/index.db' in os.fsdecode(args[0]).replace('\\','/').lower():
  raise PermissionError('Live index prohibited')
sys.addaudithook(audit)
dlls=r/'_scratch/torchcodec-native-01'
for row in json.loads((dlls/'receipt.json').read_text(encoding='utf8'))['files']:
 with Path(row['path']).open('rb') as stream:assert hashlib.file_digest(stream,'sha256').hexdigest()==row['sha256']
handle=os.add_dll_directory(str(dlls))
result={'python':sys.version,'dll_directory':str(dlls),'status':'running','model_invoked':False}
try:
 import torch,torchcodec
 from torchcodec.decoders import AudioDecoder
 path=out/'generated-silence.wav'
 with wave.open(str(path),'wb') as wav:
  wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*16000)
 samples=AudioDecoder(str(path),sample_rate=16000,num_channels=1).get_all_samples()
 assert samples.sample_rate==16000 and list(samples.data.shape)==[1,16000]
 assert torch.count_nonzero(samples.data).item()==0
 result.update(status='passed',sample_rate=samples.sample_rate,shape=list(samples.data.shape),torch_version=torch.__version__,torchcodec_version=torchcodec.__version__)
except BaseException as exc:
 import traceback
 result.update(status='failed',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc());raise
finally:
 result['guard_events']=events
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2))
