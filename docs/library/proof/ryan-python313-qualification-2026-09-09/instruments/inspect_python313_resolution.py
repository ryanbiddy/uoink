"""Read the completed UTF-8 pip receipt; no resolver or execution rerun."""
import json,re
from pathlib import Path
r=Path(__file__).resolve().parents[1];out=r/'_scratch/python313-graph-01'
normalize=lambda s:re.sub(r'[-_.]+','-',s).lower()
locked={normalize(line.split('==')[0]):line.split('==')[1] for line in (r/'requirements-installer-lock.txt').read_text(encoding='utf8').splitlines() if line and not line.startswith('#')}
report=json.loads((out/'resolution.json').read_text(encoding='utf8'))
actual={normalize(x['metadata']['name']):x['metadata']['version'] for x in report['install']}
build_only={n:actual.pop(n) for n in ('setuptools','pip','wheel') if n in actual}
assert not any('-cp313t-' in x['download_info']['url'] for x in report['install'])
diff={'expected_count':len(locked),'resolved_runtime_count':len(actual),'missing':sorted(set(locked)-set(actual)),'extra':sorted(set(actual)-set(locked)),'changed':{n:[locked[n],actual[n]] for n in locked.keys()&actual.keys() if locked[n]!=actual[n]},'build_only_selected_under_ignore_installed':build_only,'actual_python':report['environment'],'scope':'Actual CPython 3.13 direct-build graph. Resolver exit zero. Initial collector failed decoding UTF-8 as cp1252; this reads the same saved report, without a resolver rerun. No model execution.'}
(out/'graph-diff.json').write_text(json.dumps(diff,indent=2)+'\n',encoding='utf8');print(json.dumps(diff,indent=2))
