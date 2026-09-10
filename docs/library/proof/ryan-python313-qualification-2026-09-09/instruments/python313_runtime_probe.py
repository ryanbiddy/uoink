"""Synthetic native-library checks under the exact disposable Python; no models."""
import datetime as dt,importlib,importlib.metadata,json,os,sys,traceback
from pathlib import Path
out=Path(sys.argv[1]).resolve();assert out.is_relative_to(Path(__file__).resolve().parents[1]/'_scratch')
out.mkdir(exist_ok=False);events=[]
def audit(event,args):
 if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo','subprocess.Popen'):
  events.append({'event':event,'refused':True});raise PermissionError('Native qualification: network and subprocess denied')
 if event in ('open','sqlite3.connect') and args and isinstance(args[0],(str,bytes,os.PathLike)):
  name=os.fsdecode(args[0]).replace('\\','/').lower()
  if 'c:/users/hello/appdata/local/uoink/index.db' in name:
   events.append({'event':event,'refused':True});raise PermissionError('Live index prohibited')
sys.addaudithook(audit)
rows=[]
for name in ('PIL.Image','cryptography.fernet','mcp','pydantic','numpy','av','torch','torchaudio','torchvision','ctranslate2','onnxruntime','faster_whisper','torchcodec','clr','webview','win32api'):
 try:
  module=importlib.import_module(name)
  detail={'file':getattr(module,'__file__',None)}
  if name=='torch':
   assert module.tensor([1,2,3]).sum().item()==6;detail['synthetic_tensor_sum']=6
  if name=='torchaudio':
   import torch
   value=module.functional.resample(torch.zeros(1,1600),16000,8000)
   assert list(value.shape)==[1,800];detail['synthetic_resample_shape']=list(value.shape)
  if name=='PIL.Image':
   import io
   buffer=io.BytesIO();module.new('RGB',(4,4),(1,2,3)).save(buffer,format='PNG');buffer.seek(0)
   assert module.open(buffer).size==(4,4);detail['synthetic_png_roundtrip']=True
  if name=='clr':
   import System
   detail['clr_version']=str(System.Environment.Version)
  rows.append({'module':name,'status':'passed','detail':detail})
 except Exception as exc:
  rows.append({'module':name,'status':'failed','error':type(exc).__name__+': '+str(exc),'traceback':traceback.format_exc()})
 (out/'results.json').write_text(json.dumps(rows,indent=2)+'\n',encoding='utf8')
 (out/'guard-events.json').write_text(json.dumps(events,indent=2)+'\n',encoding='utf8')
inventory={d.metadata['Name']:d.version for d in importlib.metadata.distributions() if d.metadata['Name']}
(out/'inventory.json').write_text(json.dumps(inventory,indent=2,sort_keys=True)+'\n',encoding='utf8')
summary={'python':sys.version,'executable':sys.executable,'passed':sum(x['status']=='passed' for x in rows),'failed':sum(x['status']=='failed' for x in rows),'model_or_weights_invoked':False,'scope':'Imports and tiny synthetic tensor/audio/image operations; no application launch or model inference','finished_utc':dt.datetime.now(dt.timezone.utc).isoformat()}
(out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n',encoding='utf8');print(json.dumps(summary,indent=2))
raise SystemExit(int(summary['failed']>0))
