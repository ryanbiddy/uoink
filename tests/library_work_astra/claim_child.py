from pathlib import Path
import json,sys,time
from index import Index
from library_work import LibraryWorkService,RequestContext
root=Path(sys.argv[1]);n=sys.argv[2]
idx=Index.open(root/'fixture.db')
svc=LibraryWorkService(idx,root/'library',clock=lambda:1000)
(root/('ready'+n)).write_text('ready')
while not (root/'go').exists():time.sleep(.01)
print(json.dumps(svc.claim_work(RequestContext(authenticated=True,client_id='client'),dict(action='claim',run_id='r1',client_id='client'))))
