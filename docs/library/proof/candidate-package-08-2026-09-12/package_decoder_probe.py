"""Local image decoder and crypto round trip using exact installed dependencies."""
import argparse,datetime as dt,hashlib,json,os,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--app',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
app=a.app.resolve();out=a.out.resolve();allowed=Path(r'E:\AI\projects\uoink\installation-receipts').resolve()
assert app.is_relative_to(allowed) and out.is_relative_to(allowed) and sys.flags.isolated and sys.flags.no_site
assert Path(sys.executable).resolve()==app/'python/python.exe'
out.mkdir(exist_ok=False)
def audit(event,args):
 if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo','subprocess.Popen','sqlite3.connect'):raise PermissionError('Decoder-only probe: network, child processes and databases forbidden')
 if event=='open' and isinstance(args[0],(str,bytes,os.PathLike)):
  path=Path(os.fsdecode(args[0])).resolve()
  if not path.is_relative_to(app) and not path.is_relative_to(out):raise PermissionError('Decoder-only probe: file outside installed app/owned output')
sys.addaudithook(audit)
sys.path[:0]=[str(app),str(app/'python/Lib/site-packages')]
import importlib.metadata,io
from PIL import Image
import images
from cryptography.fernet import Fernet
versions={name:importlib.metadata.version(name) for name in ('Pillow','cryptography','mcp','nltk')}
assert versions=={'Pillow':'12.3.0','cryptography':'50.0.1','mcp':'1.28.1','nltk':'3.10.3'},versions
assert Path(images.__file__).resolve()==app/'images.py'
checks=[]
for fmt,ext,mime in (('PNG','png','image/png'),('JPEG','jpg','image/jpeg'),('WEBP','webp','image/webp')):
 buf=io.BytesIO();Image.new('RGB',(48,32),(180,83,9)).save(buf,format=fmt);raw=buf.getvalue()
 built=images.build_image(raw,caption='Synthetic installed decoder receipt',filename='fixture.'+ext)
 assert built['ok'] and built['mime']==mime and built['title']=='Synthetic installed decoder receipt'
 source=out/('fixture.'+ext);thumb=out/('thumb-'+ext+'.jpg');source.write_bytes(raw)
 dimensions=images._write_thumbnail(source,thumb);assert dimensions==(48,32)
 with Image.open(thumb) as result:assert result.format=='JPEG' and result.size==(48,32)
 checks.append({'format':fmt,'source_sha256':hashlib.sha256(raw).hexdigest(),'dimensions':dimensions,'thumbnail_sha256':hashlib.sha256(thumb.read_bytes()).hexdigest(),'passed':True})
for raw,code in ((b'','empty'),(b'ordinary non-image text','unsupported'),(b'\x89PNG\r\n\x1a\n'+b'0'*(images.MAX_IMAGE_BYTES+1),'too_large')):
 result=images.build_image(raw);assert result['ok'] is False and result['code']==code
 checks.append({'rejection':code,'passed':True})
cipher=Fernet(Fernet.generate_key());assert cipher.decrypt(cipher.encrypt(b'synthetic local probe'))==b'synthetic local probe'
checks.append({'crypto':'Fernet ephemeral in-memory round trip; no saved credential','passed':True})
report={'utc':dt.datetime.now(dt.timezone.utc).isoformat(),'versions':versions,'executable':sys.executable,'image_module':images.__file__,'checks':checks,'passed':len(checks),'scope':'Bounded compatibility observation, not a malformed-image fuzzing or security certification','network_or_model_run':False}
(out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf8',newline='\n');print(json.dumps(report,indent=2))
