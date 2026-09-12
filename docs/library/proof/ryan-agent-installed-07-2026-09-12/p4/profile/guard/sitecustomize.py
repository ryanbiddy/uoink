# P4 receipt guard. Refuse live index, port 5179, model/client/fetch.
import os, sys
from pathlib import Path
from urllib.parse import urlsplit, unquote

def database_path(value):
    if value.startswith('file:'):
        uri = urlsplit(value)
        if uri.netloc.lower() not in ('', 'localhost'):
            raise PermissionError('P4 remote database authority forbidden')
        value = unquote(uri.path)
        if os.name == 'nt' and len(value) > 2 and value[0] == '/' and value[2] == ':':
            value = value[1:]
    return Path(value).resolve()

def audit(event, args):
    forbidden = os.environ.get('P4_FORBIDDEN_INDEX', '')
    absolute_forbidden = os.environ.get('IG_FORBIDDEN_LIVE', '')
    root = os.environ.get('P4_ISOLATED_PROFILE') or os.environ.get('P4_FIXTURE_ROOT')
    if event in ('open', 'sqlite3.connect') and isinstance(args[0], (str, bytes, os.PathLike)):
        value = os.fsdecode(args[0]).replace('\\', '/').lower()
        if forbidden and forbidden.replace('\\', '/').lower() in value:
            raise PermissionError('P4 live index forbidden')
        if absolute_forbidden and absolute_forbidden.replace('\\', '/').lower() in value:
            raise PermissionError('P4 integrator live index forbidden')
    if event == 'sqlite3.connect' and isinstance(args[0], str) and args[0] != ':memory:' and root:
        if not database_path(args[0]).is_relative_to(Path(root).resolve()):
            raise PermissionError('P4 database outside isolated profile')
    if event in ('socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'):
        address = args[:2] if event == 'socket.getaddrinfo' else args[1]
        if isinstance(address, tuple) and (
            str(address[1]) == '5179' or address[0] not in ('127.0.0.1', '::1', 'localhost', '')
        ):
            raise PermissionError('P4 external network or resident port forbidden')
    if event == 'subprocess.Popen':
        command = args[1]
        first = command[0] if isinstance(command, (tuple, list)) else str(command).split()[0]
        name = Path(str(first)).stem.lower()
        if name in ('claude', 'codex', 'grok', 'gemini', 'yt-dlp', 'ffmpeg', 'curl'):
            raise PermissionError('P4 execution/fetch sentinel')

sys.addaudithook(audit)
