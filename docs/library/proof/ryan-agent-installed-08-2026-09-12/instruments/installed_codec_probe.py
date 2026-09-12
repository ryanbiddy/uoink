"""Use actual installed Python and the product DLL loader to decode generated PCM."""
import argparse,hashlib,json,os,sys,wave
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--app',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
app=a.app.resolve();out=a.out.resolve();allowed=Path(r'E:\AI\projects\uoink\installation-receipts')
assert app.is_relative_to(allowed) and out.is_relative_to(allowed) and sys.flags.isolated and sys.flags.no_site
assert Path(sys.executable).resolve()==app/'python/python.exe'
out.mkdir(exist_ok=False)
events=[]
def audit(event,args):
 if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo','subprocess.Popen','sqlite3.connect'):
  events.append({'event':event,'refused':True});raise PermissionError('Installed native probe forbids network, processes and databases')
 if event=='open' and args and isinstance(args[0],(str,bytes,os.PathLike)) and 'c:/users/hello/appdata/local/uoink/index.db' in os.fsdecode(args[0]).replace('\\','/').lower():
  raise PermissionError('Live index prohibited')
sys.addaudithook(audit)
sys.path[:0]=[str(app),str(app/'python/Lib/site-packages')]
result={'status':'running','python':sys.version,'executable':sys.executable,'app':str(app),'model_invoked':False}
try:
 import whisper_runner
 assert Path(whisper_runner.__file__).resolve()==app/'whisper_runner.py'
 assert whisper_runner._PACKAGED_DECODER_DLL_HANDLE is not None
 import torch,torchcodec
 from torchcodec.decoders import AudioDecoder
 source=out/'generated-silence.wav'
 with wave.open(str(source),'wb') as wav:
  wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*16000)
 samples=AudioDecoder(str(source),sample_rate=16000,num_channels=1).get_all_samples()
 assert samples.sample_rate==16000 and list(samples.data.shape)==[1,16000]
 assert torch.count_nonzero(samples.data).item()==0
 result.update(status='passed',shape=list(samples.data.shape),sample_rate=samples.sample_rate,torch_version=torch.__version__,torchcodec_version=torchcodec.__version__,product_module_sha256=hashlib.sha256((app/'whisper_runner.py').read_bytes()).hexdigest())
except BaseException as exc:
 import traceback
 result.update(status='failed',error=type(exc).__name__+': '+str(exc),traceback=traceback.format_exc());raise
finally:
 result['guard_events']=events
 (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result,indent=2))
