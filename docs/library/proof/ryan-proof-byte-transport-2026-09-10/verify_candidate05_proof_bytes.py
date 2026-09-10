import argparse,hashlib,io,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--ref',default='');p.add_argument('--out',required=True,type=Path);p.add_argument('--include-transport',action='store_true');args=p.parse_args()
r=Path(__file__).resolve().parents[1]
names=['ryan-p4-embedded-probe-2026-09-10','ryan-final-partitioned-02-2026-09-10','ryan-agent-installed-05-2026-09-09','product-suite-review-2026-09-10']
if args.include_transport:names.append('ryan-proof-byte-transport-2026-09-10')
expected=[]
for name in names:
 folder='docs/library/proof/'+name
 manifest=json.loads((r/folder/'SHA256.json').read_text(encoding='utf8'))
 for file,row in manifest['files'].items():
  path=folder+'/'+file;raw=(r/path).read_bytes()
  assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],path
  expected.append((path,row))
refs=''.join(args.ref+':'+path+'\n' for path,row in expected).encode()
stream=io.BytesIO(subprocess.check_output(['git','cat-file','--batch'],cwd=r,input=refs))
for path,row in expected:
 head=stream.readline().split();assert len(head)==3 and head[1]==b'blob',(path,head)
 raw=stream.read(int(head[2]));assert stream.read(1)==b'\n'
 assert len(raw)==row['bytes'] and hashlib.sha256(raw).hexdigest()==row['sha256'],path
report={'status':'PASS','ref':args.ref or 'staged index','head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=r,text=True).strip(),'payloads_verified':len(expected),'proofs':names,'scope':'Every local and Git object payload matches its retained byte count and SHA-256. Existing failed/partial measurements are unchanged.'}
with args.out.open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(report,indent=2)+'\n')
print(json.dumps(report))
