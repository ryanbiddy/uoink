"""Retain receipt-only path/date adaptations before the fresh installed run."""
from pathlib import Path
import ast,difflib,hashlib,json
r=Path(__file__).resolve().parent
changes=[]
for oldname,newname in (('inventory_installed_extras06.py','inventory_installed_extras07.py'),
                        ('run_installed_decoders06.py','run_installed_decoders07.py'),
                        ('run_installed_decoders06_portable.py','run_installed_decoders07_portable.py')):
    old=(r/oldname).read_text(encoding='utf8')
    new=old.replace('Agent Install 06','Agent Install 07').replace('candidate-package-06-2026-09-11','candidate-package-07-2026-09-12')
    ast.parse(new)
    with (r/newname).open('x',encoding='utf8',newline='\n') as f:f.write(new)
    delta=''.join(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile=oldname,tofile=newname))
    with (r/(newname+'.diff')).open('x',encoding='utf8',newline='\n') as f:f.write(delta)
    changes.append({'before':oldname,'after':newname,'scope':'Exact app/seal labels only; original assertions, probes and startup restoration retained.',
                    'before_sha256':hashlib.sha256((r/oldname).read_bytes()).hexdigest(),
                    'after_sha256':hashlib.sha256((r/newname).read_bytes()).hexdigest(),
                    'executed':False})
with (r/'installed07-instrument-adaptations.json').open('x',encoding='utf8',newline='\n') as f:f.write(json.dumps(changes,indent=2)+'\n')
print(json.dumps(changes,indent=2))
