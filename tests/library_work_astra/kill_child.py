from pathlib import Path
import os,sys,time
from index import Index
from library_work import LibraryWorkService,RequestContext,decode_json
root=Path(sys.argv[1]); boundary=sys.argv[2]
def hook(point):
    if point==boundary:
        with open(root/'barrier','w') as stream:
            stream.write(point);stream.flush();os.fsync(stream.fileno())
        while True:time.sleep(1)
idx=Index.open(root/'fixture.db')
svc=LibraryWorkService(idx,root/'library',clock=lambda:1000,crash_hook=hook)
ctx=RequestContext(authenticated=True,client_id='client',session_id='local',operator=True,local_user_confirmed=True)
print(svc.pin_shelf(ctx,decode_json((root/'request.json').read_bytes())),flush=True)
