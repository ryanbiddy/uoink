import difflib
from pathlib import Path
r=Path(__file__).resolve().parents[1]
p=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini\server.py')
old=p.read_text(encoding='utf8')
needle='''            data = json.loads(content.decode("utf-8"), parse_float=finite_float,
                              parse_constant=reject_constant)
'''
assert old.count(needle)==1
new=old.replace(needle,needle+'''            # Enforce an explicit bound independent of the process recursion limit.
            pending = [(data, 0)]
            while pending:
                value, depth = pending.pop()
                if isinstance(value, (dict, list)):
                    if depth >= 64:
                        raise ValueError("sidecar JSON too deeply nested")
                    children = value.values() if isinstance(value, dict) else value
                    pending.extend((child, depth + 1) for child in children)
''')
out=r/'_scratch/media-detail12-review'
(out/'astra-server-depth-original.txt').write_bytes(p.read_bytes())
(out/'astra-server-depth.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='implicit-recursion-bound',tofile='explicit-depth-bound')),encoding='utf8')
(out/'depth-repair-brief.md').write_text('''# Explicit saved-JSON depth bound

astra-media12-repair-worker01 has 56 passes and one failure. A 1,500-level
synthetic document parsed under this process and was returned as success after
field filtering. Catching RecursionError alone is not a depth contract. Add an
iterative maximum of 64 container levels before filtering, while retaining the
2 MiB byte cap and the existing exception handling. Keep all assertions. Then
run the unchanged 57-case union under fresh astra-media12-repair-worker02.
''',encoding='utf8')
p.write_text(new,encoding='utf8',newline='\n')
print('Recorded failure and added explicit 64-level JSON bound.')
