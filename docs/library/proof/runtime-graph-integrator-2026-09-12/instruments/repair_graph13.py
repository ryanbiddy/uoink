"""Integrator edits after preserving the unaccepted checker and its tests."""
import ast
from pathlib import Path

path=Path(r'C:\Users\hello\AppData\Local\AgentControlRoom\worktrees\uoink-library\6c96f0a3-c02\gemini\scripts\check_runtime_graph.py')
source=path.read_text(encoding='utf8')
def replace(old,new):
    global source
    assert source.count(old)==1, old[:100]
    source=source.replace(old,new)
def function(name,new):
    global source
    node=next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name)
    lines=source.splitlines(keepends=True)
    source=''.join(lines[:node.lineno-1])+new.strip()+'\n'+''.join(lines[node.end_lineno:])

replace('from pathlib import Path, PurePosixPath','from pathlib import Path, PurePosixPath, PureWindowsPath\nimport os\nimport stat\nfrom urllib.parse import urlsplit')
helpers=r'''
def _unique_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('Duplicate JSON key: ' + key)
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def _no_links(path):
    for parent in [*reversed(path.absolute().parents), path.absolute()]:
        try:
            info = parent.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Symlink/reparse evidence path: ' + str(parent))


def _bounded_path(root, relative):
    root = Path(root).absolute()
    if '..' in root.parts or str(root).startswith(('\\\\', '//')):
        raise ValueError('Unsafe evidence root')
    _no_links(root)
    if not isinstance(relative, str) or not relative or '\x00' in relative:
        raise ValueError('Invalid evidence path')
    relative = relative.replace('\\', '/')
    win = PureWindowsPath(relative)
    if win.drive or win.root or relative.startswith('/'):
        raise ValueError('Absolute path in evidence')
    parts = PurePosixPath(relative).parts
    if '..' in parts:
        raise ValueError('Path traversal in evidence')
    for part in parts:
        if ':' in part or part.rstrip(' .') != part or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9])(?:\..*)?', part):
            raise ValueError('Device/stream evidence path refused')
    result = root.joinpath(*parts)
    if result == root:
        raise ValueError('Evidence must name a file')
    _no_links(result)
    return result


def _covered_bytes(root, relative, verified):
    path = _bounded_path(root, relative)
    key = path.relative_to(Path(root).absolute()).as_posix()
    if not isinstance(verified, dict) or key not in verified:
        raise ValueError('Manifest coverage failure: ' + key)
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != verified[key]:
        raise ValueError('Evidence changed after manifest verification: ' + key)
    return path, data


def _artifact_url(url):
    if not isinstance(url, str) or re.search(r'[\x00-\x20\\]', url):
        return False
    try:
        parsed = urlsplit(url)
        return (parsed.scheme == 'https' and bool(parsed.hostname) and
                parsed.username is None and parsed.password is None and
                not parsed.fragment and parsed.port in (None, 443))
    except ValueError:
        return False


'''
replace('def canonical_name(value: str) -> str:',helpers+'def canonical_name(value: str) -> str:')
replace('name, _, ver = match.groups()', 'name, extras, ver = match.groups()')
replace('if cname in locked:\n            raise ValueError', 'if cname in [key.split("[")[0] for key in locked]:\n            raise ValueError')
replace('locked[cname] = ver\n    return locked', 'locked[f"{cname}[{extras}]" if extras else cname] = ver\n    return locked')
replace('data = json.loads(text)', 'data = _unique_json(text)')
replace('if k.startswith("_"):\n                    continue', 'if k.startswith("_"):\n                    raise ValueError("Invalid package name in selection: " + k)')
replace('msg = email.message_from_string(content)', '''msg = email.message_from_string(content)
    for singleton in ('Name', 'Version', 'Requires-Python'):
        if len(msg.get_all(singleton) or []) > 1:
            raise ValueError('Duplicate METADATA singleton: ' + singleton)''')
function('verify_evidence_integrity',r'''
def verify_evidence_integrity(proof_dir):
    """Verify retained byte hashes before any dependent evidence is consumed."""
    verified, seen, errors = {}, set(), []
    try:
        manifest_path = None
        for name in ('SHA256.json', 'manifest.json', 'evidence_manifest.json'):
            candidate = _bounded_path(proof_dir, name)
            if candidate.is_file():
                manifest_path = candidate
                break
        if manifest_path is None:
            return False, ['Missing evidence manifest'], {}
        raw = manifest_path.read_text(encoding='utf8')
        if not raw:
            return False, ['Empty manifest'], {}
        try:
            parsed = _unique_json(raw)
        except ValueError as exc:
            return False, ['Malformed manifest JSON: ' + str(exc)], {}
        files = parsed.get('files', parsed) if isinstance(parsed, dict) else None
        if not isinstance(files, dict) or not files:
            return False, ['Manifest contains no entries'], {}
        for name, value in files.items():
            try:
                digest = value.get('sha256') if isinstance(value, dict) else value
                if not isinstance(digest, str) or not SHA256_HEX_REGEX.fullmatch(digest):
                    raise ValueError('Invalid SHA256 value for ' + str(name))
                target = _bounded_path(proof_dir, name)
                key = target.relative_to(Path(proof_dir).absolute()).as_posix()
                if key.casefold() in seen:
                    raise ValueError('Duplicate normalized manifest entry: ' + name)
                seen.add(key.casefold())
                actual = hashlib.sha256(target.read_bytes()).hexdigest()
                if actual != digest.lower():
                    raise ValueError('Tampered/mismatched evidence: ' + name)
                verified[key] = actual
            except (OSError, ValueError) as exc:
                errors.append(str(exc))
    except (OSError, ValueError) as exc:
        errors.append(str(exc))
    return not errors, errors, verified
''')
function('find_pypi_json_for_package',r'''
def find_pypi_json_for_package(proof_dir, cname, version=None, verified_files=None):
    """Read only an enumerated package record, bound to its manifest bytes."""
    names = ([f'{cname}-{version}.json', f'{cname}@{version}.json'] if version else [])
    names += [f'{cname}.json', f"{cname.replace('-', '_')}.json", f"{cname.replace('-', '.')}.json"]
    try:
        for name in dict.fromkeys(names):
            relative = 'pypi/' + name
            candidate = _bounded_path(proof_dir, relative)
            if candidate.is_file():
                path, data = _covered_bytes(proof_dir, relative, verified_files)
                parsed = _unique_json(data.decode('utf8'))
                if not isinstance(parsed, dict) or not isinstance(parsed.get('info', {}), dict):
                    raise ValueError('Malformed PyPI record structure')
                if not isinstance(parsed.get('releases', {}), dict) or not isinstance(parsed.get('urls', []), list):
                    raise ValueError('Malformed PyPI release structure')
                info_name = parsed.get('info', {}).get('name')
                if info_name is not None and canonical_name(info_name) != cname:
                    raise ValueError('PyPI package Name mismatch')
                return path, parsed, []
    except (OSError, ValueError, TypeError, UnicodeError) as exc:
        return None, None, [str(exc)]
    return None, None, [f"PyPI JSON not found for package '{cname}'"]
''')
start=source.index('    meta_dir = proof_dir / "metadata"',source.index('def find_exact_wheel_metadata_file'))
end=source.index('    # Validate Name and Version match selected package',start)
source=source[:start]+'''    relative = 'metadata/' + wheel_filename + '.metadata'
    errors = []
    try:
        target_file, data = _covered_bytes(proof_dir, relative, verified_files)
        parsed = parse_metadata_text(data.decode('utf8'))
    except (OSError, ValueError, UnicodeError) as exc:
        return None, None, ['Missing or invalid exact wheel METADATA: ' + str(exc)]

'''+source[end:]
replace('for file_info in release_files:\n        filename = file_info.get("filename", "")', '''if not isinstance(release_files, list):
        return {'status': 'NO_WHEELS', 'error': 'Malformed release files list'}
    for file_info in release_files:
        if not isinstance(file_info, dict) or not isinstance(file_info.get('filename'), str):
            rejected_invalid.append('Malformed wheel record')
            continue
        filename = file_info.get("filename", "")''')
replace('if not url or not isinstance(url, str) or not (url.startswith("http://") or url.startswith("https://")):', 'if not _artifact_url(url):')
replace('digests = file_info.get("digests") or {}\n        sha256', '''digests = file_info.get("digests") or {}
        if not isinstance(digests, dict):
            rejected_invalid.append('Malformed wheel digests')
            continue
        sha256''')
replace('for raw_k, ver_str in selection.items():\n        if', '''for raw_k, ver_str in selection.items():
        if not isinstance(raw_k, str) or not isinstance(ver_str, str):
            selection_errors.append('Package and version must be strings')
            continue
        if''')
replace('for cname, version in sorted(selected_versions.items()):', 'for cname, version in (sorted(selected_versions.items()) if manifest_ok else []):')
replace('    # Step 3: Evaluate PEP 508 active edges, markers, and constraints', '''    if changed:
        selection_errors.append('Extras propagation did not converge')

    # Step 3: Evaluate PEP 508 active edges, markers, and constraints''')
ast.parse(source)
path.write_text(source,encoding='utf8',newline='\n')
print('Applied bounded graph repairs; original source archive unchanged')
