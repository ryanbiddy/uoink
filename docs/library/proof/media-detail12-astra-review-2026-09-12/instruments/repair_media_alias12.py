from pathlib import Path
import difflib
r=Path(__file__).resolve().parents[1]
w=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\2dae80cc-01a\gemini')
p=w/'server.py';old=p.read_text(encoding='utf8');s=old
start=s.index('    def _handle_yoink_details');head=s[:start];body=s[start:]
needle='for k in ("start", "end", "text", "content", "speaker",'
assert body.count(needle)==1
body=body.replace(needle,'for k in ("start", "start_seconds", "end", "end_seconds", "text", "content", "speaker",')
needle='k: s[k] for k in ("start", "end", "speaker",'
assert body.count(needle)==1
body=body.replace(needle,'k: s[k] for k in ("start", "start_seconds", "end", "end_seconds", "speaker",')
s=head+body;p.write_text(s,encoding='utf8',newline='\n')
(r/'_scratch/media-detail12-review/astra-time-alias.diff').write_text(''.join(difflib.unified_diff(old.splitlines(True),s.splitlines(True),fromfile='before/server.py',tofile='after/server.py')),encoding='utf8')
