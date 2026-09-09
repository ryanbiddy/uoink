import json,os,sys,sitecustomize
from pathlib import Path
canary=Path(os.environ['IG_FORBIDDEN_LIVE'])
try:
    canary.write_text('must not write')
except PermissionError:
    refused=True
else:
    refused=False
assert refused and not canary.exists()
print(json.dumps({'pid':os.getpid(),'guard':sitecustomize.__file__,'canary_refused':refused,'executable':sys.executable,'version':sys.version}))
