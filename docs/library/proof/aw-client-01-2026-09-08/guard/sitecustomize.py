import os,sys
from pathlib import Path
from urllib.parse import urlsplit,unquote
def database_path(value):
    if value.startswith('file:'):
        uri=urlsplit(value)
        if uri.netloc.lower() not in ('','localhost'):
            raise PermissionError('AW remote database authority forbidden')
        value=unquote(uri.path)
        if os.name=='nt' and len(value)>2 and value[0]=='/' and value[2]==':':
            value=value[1:]
    return Path(value).resolve()
def audit(event,args):
    if event in ('open','sqlite3.connect') and isinstance(args[0],(str,bytes,os.PathLike)):
        value=os.fsdecode(args[0]).replace('\\','/').lower()
        if os.environ['AW_FORBIDDEN_INDEX'].replace('\\','/').lower() in value:
            raise PermissionError('AW live index forbidden')
    if event=='sqlite3.connect' and isinstance(args[0],str) and args[0]!=':memory:':
        if not database_path(args[0]).is_relative_to(Path(os.environ['AW_FIXTURE_ROOT']).resolve()):
            raise PermissionError('AW database outside fixture')
    if event in ('socket.connect','socket.bind','socket.sendto','socket.getaddrinfo'):
        address=args[:2] if event=='socket.getaddrinfo' else args[1]
        if isinstance(address,tuple) and (str(address[1])=='5179' or address[0] not in ('127.0.0.1','::1','localhost','')):
            raise PermissionError('AW external network or resident port forbidden')
    if event=='subprocess.Popen':
        command=args[1]
        first=command[0] if isinstance(command,(tuple,list)) else str(command).split()[0]
        if Path(str(first)).stem.lower() in ('claude','codex','grok','gemini','yt-dlp','ffmpeg','curl'):
            raise PermissionError('AW execution/fetch sentinel')
sys.addaudithook(audit)
