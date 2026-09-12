"""Check all declared Windows/Python 3.13 runtime dependency edges in staging."""
import email
import hashlib
import json
from pathlib import Path
import sys

r = Path(__file__).resolve().parents[1]
site = r / 'installer/staging/python/Lib/site-packages'
sys.path.insert(0, str(site))
from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

out = r / '_scratch/package07-runtime-graph-01'
out.mkdir(exist_ok=False)
lock_path = r / 'requirements-installer-lock.txt'
lock = {canonicalize_name(line.split('==')[0]): line.split('==')[1]
        for line in lock_path.read_text().splitlines() if line and not line.startswith('#')}
metadata = {}
for path in site.glob('*.dist-info/METADATA'):
    data = email.message_from_bytes(path.read_bytes())
    name = canonicalize_name(data['Name'])
    assert name not in metadata, name
    metadata[name] = data
inventory = {name: data['Version'] for name, data in metadata.items()}
(out / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf8')
assert len(lock) == 140 and inventory == lock
env = default_environment()
env.update(python_version='3.13', python_full_version='3.13.15', sys_platform='win32',
           platform_system='Windows', os_name='nt', platform_machine='AMD64')
extras = {name: set() for name in lock}
edges = {}
for iteration in range(20):
    changed = False
    for name, data in metadata.items():
        for raw in data.get_all('Requires-Dist', []):
            req = Requirement(raw)
            if req.marker and not any(req.marker.evaluate(dict(env, extra=e)) for e in {'', *extras[name]}):
                continue
            dep = canonicalize_name(req.name)
            satisfied = dep in lock and (not req.specifier or req.specifier.contains(lock[dep], prereleases=True))
            edges[(name, raw)] = {'source': name, 'requirement': raw, 'version': lock.get(dep),
                                  'satisfied': bool(satisfied)}
            if dep in extras:
                new = set(req.extras) - extras[dep]
                if new:
                    extras[dep].update(new)
                    changed = True
    if not changed:
        break
else:
    raise AssertionError('Dependency extras did not converge')
rows = list(edges.values())
bad = [row for row in rows if not row['satisfied']]
summary = {'pins': len(lock), 'dependency_edges': len(rows), 'failed_edges': bad,
           'activated_extras': {name: sorted(values) for name, values in extras.items() if values},
           'lock_sha256': hashlib.sha256(lock_path.read_bytes()).hexdigest(),
           'scope': 'All top-level installed distribution metadata, evaluated for Windows Python 3.13.15; no inference',
           'rows': rows}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
print(json.dumps({k: v for k, v in summary.items() if k != 'rows'}, indent=2))
raise SystemExit(int(bool(bad)))
