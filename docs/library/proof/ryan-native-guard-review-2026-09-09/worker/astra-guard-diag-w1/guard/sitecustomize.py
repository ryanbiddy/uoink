import os, sys
def audit(event, args):
    if event in ('open', 'sqlite3.connect'):
        value = args[0]
        if isinstance(value, (str, bytes, os.PathLike)):
            name = os.fsdecode(value).replace('\\', '/').lower()
            forbidden = os.environ['IG_FORBIDDEN_LIVE'].replace('\\', '/').lower()
            if forbidden in name:
                raise PermissionError('Integrator guard: live index forbidden')
    if event in ('socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo'):
        addr = args[:2] if event == 'socket.getaddrinfo' else args[1]
        if isinstance(addr, tuple) and (str(addr[1]) == '5179' or addr[0] not in ('127.0.0.1', '::1', 'localhost', '0.0.0.0', '')):
            raise PermissionError('Integrator guard: external network / 5179 forbidden')
    if event == 'subprocess.Popen':
        cmd = args[1]
        first = cmd[0] if isinstance(cmd, (list, tuple)) and cmd else str(cmd).split()[0]
        name = os.path.basename(str(first)).lower().strip('"')
        if name.split('.')[0] in ('claude','codex','gemini','grok'):
            raise PermissionError('Integrator guard: real model process forbidden')
sys.addaudithook(audit)
