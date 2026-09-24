from pathlib import Path
import os,sys
from index import Index
from library_work import LibraryWorkService,RequestContext,decode_json
root=Path(sys.argv[1]); boundary=sys.argv[2]
idx=Index.open(root/'fixture.db')
svc=LibraryWorkService(idx,root/'library',clock=lambda:1000,crash_hook=lambda point: os._exit(73) if point==boundary else None)
ctx=RequestContext(authenticated=True,client_id='client',session_id='local',operator=True,local_user_confirmed=True)
print(svc.pin_shelf(ctx,decode_json((root/'request.json').read_bytes())),flush=True)
raise SystemExit(1)
