import os,sys
from pathlib import Path
allowed=Path('E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\_scratch\\packaged-runtime-01').resolve()
for key in ('LOCALAPPDATA','APPDATA','TEMP','TMP'):
 assert Path(os.environ[key]).resolve().is_relative_to(allowed)
def audit(event,args):
 if event in ('open','sqlite3.connect') and isinstance(args[0],(str,bytes,os.PathLike)):
  path=os.fsdecode(args[0]).replace('\\','/').lower()
  if 'c:/users/hello/appdata/local/uoink/index.db' in path:raise PermissionError('Live index forbidden')
 if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'):
  raise PermissionError('Network forbidden in staged runtime observation')
 if event=='subprocess.Popen':
  raise PermissionError('No nested process in staged stdio observation')
sys.addaudithook(audit)
sys.path.insert(0,'E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\installer\\staging')
import runpy
runpy.run_path('E:\\AI\\projects\\uoink\\checkouts\\Yoink-library\\installer\\staging\\uoink_mcp.py',run_name="__main__")
