from pathlib import Path
import difflib
out=Path(__file__).resolve().parent
before=(out/'inventory.py').read_text(encoding='utf-8')
assert before.count("'.ps1','.cfg'")==1
after=before.replace("'.ps1','.cfg'","'.ps1','.cfg','.html'",1)
with (out/'inventory02.py').open('x',encoding='utf-8',newline='\n') as stream:stream.write(after)
with (out/'inventory-repair.patch').open('x',encoding='utf-8',newline='\n') as stream:
    stream.write(''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='inventory01.py',tofile='inventory02.py')))
