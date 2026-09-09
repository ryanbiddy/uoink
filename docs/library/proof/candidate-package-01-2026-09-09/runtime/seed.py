import os,sys,socket
from pathlib import Path
allowed=Path('E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\packaged-runtime-02').resolve()
socketpair_code=socket.socketpair.__code__
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP'):
 assert Path(os.environ[key]).resolve().is_relative_to(allowed)
def audit(event,args):
 if event in ('open','sqlite3.connect') and isinstance(args[0],(str,bytes,os.PathLike)):
  path=os.fsdecode(args[0]).replace('\\','/').lower()
  if 'c:/users/hello/appdata/local/uoink/index.db' in path:raise PermissionError('Live index forbidden')
 if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'):
  caller=sys._getframe(1)
  if event in ('socket.bind','socket.connect') and caller.f_code is socketpair_code:
   address=args[1];local=caller.f_locals
   if address[0] in ('127.0.0.1','::1') and address[1]!=5179:
    if event=='socket.bind' and args[0] is local.get('lsock') and address[1]==0:return
    if event=='socket.connect' and args[0] is local.get('csock') and address[:2]==local['lsock'].getsockname()[:2]:return
  raise PermissionError('Network forbidden in staged runtime observation')
 if event=='subprocess.Popen':
  raise PermissionError('No nested process in staged stdio observation')
sys.addaudithook(audit)
sys.path.insert(0,'E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\installer\\staging')
import importlib.metadata,json
import index,library_cards,library_work,source_subscriptions,library_resources,library_prompts,library_briefs,library_mirror,library_media,library_faithfulness
from pathlib import Path
root=Path('E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\packaged-runtime-02');data=root/'profile'/'Uoink';data.mkdir(parents=True,exist_ok=True)
(data/'settings.json').write_text(json.dumps({'librarian_apply_enabled':False}),encoding='utf-8')
corpus=root/'corpus.md';corpus.write_text('# Packaged orbit fixture\n\nThe stored value is BLUE.\n',encoding='utf-8')
idx=index.Index.open(data/'index.db')
try:
 idx.upsert_yoink({'video_id':'packaged-orbit','slug':'packaged-orbit','title':'Packaged orbit fixture','channel':'Synthetic fixture','topic':'orbit','yoinked_at':'2026-09-08T00:00:00Z','source_type':'note','platform':'note','corpus_path':str(corpus),'sidecar_path':str(root/'unused.json'),'metadata_json':json.dumps({'url':'https://example.invalid/packaged-orbit'})},content='The stored value is BLUE.')
 result={'python':sys.version,'mcp':importlib.metadata.version('mcp'),'schema':idx._conn.execute('SELECT MAX(version) FROM schema_version').fetchone()[0],'items':idx._conn.execute('SELECT COUNT(*) FROM yoinks').fetchone()[0]}
finally:idx.close()
print(json.dumps(result))
