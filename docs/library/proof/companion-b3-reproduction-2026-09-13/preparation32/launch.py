"""Prepared B3 builds; reuse verified private runtime, never copy it."""
import sys
if tuple(sys.version_info[:3]) != (3, 14, 6) or not (sys.flags.isolated and sys.flags.no_site and sys.flags.dont_write_bytecode) or "site" in sys.modules:
    raise RuntimeError("Requires reviewed Python 3.14.6 -I -S -B")
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import traceback
OUT = Path(__file__).absolute().parent
SCRATCH = OUT.parent
RUNTIME = SCRATCH / "b2-stdlib313-runtime01"
PLAN_HASH = "8b676299c1e60414231ffefcf62bd00705c6f24d633a9aa23e91a1829b618b0b"
PTH = b"python313.zip\n.\n"
CAP = 8 * 1024 * 1024
digest = lambda raw: hashlib.sha256(raw).hexdigest()

def no_links(path):
    for part in (*reversed(path.parents), path):
        try:
            data = part.lstat()
        except FileNotFoundError:
            continue
        if stat.S_ISLNK(data.st_mode) or getattr(data, "st_reparse_tag", 0) or getattr(data, "st_file_attributes", 0) & 0x400:
            raise ValueError("Linked or reparse path refused")

def bounded(path, size):
    if not isinstance(size, int) or not 0 <= size <= CAP:
        raise ValueError("Invalid read bound")
    no_links(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size != size:
        raise ValueError("Regular exact-sized input required")
    identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if not stat.S_ISREG(opened.st_mode) or identity(opened) != identity(before):
            raise ValueError("Input changed before open")
        raw = stream.read(size + 1)
        if len(raw) != size or identity(os.fstat(stream.fileno())) != identity(opened):
            raise ValueError("Input changed during bounded read")
    no_links(path)
    if identity(path.lstat()) != identity(before):
        raise ValueError("Input pathname changed")
    return raw

def write_json(directory, name, value):
    no_links(directory)
    with (directory / name).open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2) + "\n")

def verify_preparation(expected):
    if not re.fullmatch("[a-f0-9]{64}", expected):
        raise ValueError("An externally reviewed preparation seal is required")
    seal = OUT / "SHA256.json"
    no_links(seal)
    size = seal.stat().st_size
    if size > 256 * 1024:
        raise ValueError("Preparation manifest exceeds cap")
    raw = bounded(seal, size)
    if digest(raw) != expected:
        raise ValueError("Externally pinned preparation seal mismatch")
    rows = json.loads(raw)["payloads"]
    names = set()
    for row in rows:
        name = row["file"]
        path = Path(name)
        if path.is_absolute() or ".." in path.parts or ":" in name or name in names or row["bytes"] > 1024 * 1024:
            raise ValueError("Invalid/duplicate preparation member")
        names.add(name)
        if digest(bounded(OUT / path, row["bytes"])) != row["sha256"]:
            raise ValueError("Preparation input mismatch: " + name)
    return rows

def plan():
    source = OUT / "runtime-copy-plan.json"
    raw = bounded(source, source.stat().st_size)
    if digest(raw) != PLAN_HASH:
        raise ValueError("Prior exact runtime plan mismatch")
    data = json.loads(raw)
    if Path(data["source_directory"]) != SCRATCH / "python313-graph-01/python" or Path(data["proposed_private_directory"]) != RUNTIME:
        raise ValueError("Unexpected runtime roots")
    names = [row["filename"] for row in data["files"]]
    if len(names) != 33 or len(set(names)) != 33 or any(Path(name).name != name or ":" in name or name == "python313._pth" for name in names):
        raise ValueError("Unexpected runtime member set")
    if data["private_pth"]["text"].encode() != PTH or digest(PTH) != data["private_pth"]["sha256"]:
        raise ValueError("Private no-site configuration mismatch")
    return data

def verify_runtime(data):
    no_links(RUNTIME)
    expected = {row["filename"] for row in data["files"]} | {"python313._pth"}
    names = []
    for path in RUNTIME.iterdir():
        names.append(path.name)
        if len(names) > 34:
            raise ValueError("Unexpected runtime entry count")
    if set(names) != expected:
        raise ValueError("Unexpected runtime files or directories")
    for row in data["files"]:
        if digest(bounded(RUNTIME / row["filename"], row["bytes"])) != row["sha256"]:
            raise ValueError("Private runtime hash mismatch")
    if bounded(RUNTIME / "python313._pth", len(PTH)) != PTH:
        raise ValueError("Private no-site configuration mismatch")

def fresh(path):
    no_links(path)
    if not path.parent.is_dir():
        raise ValueError("Existing scratch parent required")
    path.mkdir(exist_ok=False)

def build(data, seal, label, comparison_sha=None, comparison_size=None):
    run = SCRATCH / ('b3-real-wheel-' + label)
    if label == 'py313-01':
        verify_runtime(data)
        first = SCRATCH / 'b3-real-wheel-py314-01'
        first_receipt = first / 'build-result.json'
        receipt = json.loads(bounded(first_receipt, first_receipt.stat().st_size))
        first_plan = first / 'launch-plan.json'
        launched = json.loads(bounded(first_plan, first_plan.stat().st_size))
        first_exit = first / 'launch-result.json'
        actual = json.loads(bounded(first_exit, first_exit.stat().st_size))
        expected_path = first / 'artifact/faster_whisper-1.2.1+uoink.localassets2-py3-none-any.whl'
        if (receipt.get('status') != 'BUILT_AND_BYTE_VERIFIED' or receipt.get('exit') != 0
            or receipt.get('guard', {}).get('valid') is not True
            or receipt.get('builder_sha256') != 'f25530a3ee58169c049e63c2e6bfff444061f2c04c9a87ec2af43c8850b81892'
            or receipt['output']['sha256'] != comparison_sha or receipt['output']['size'] != comparison_size
            or Path(receipt['output']['path']) != expected_path or launched['manifest_sha256'] != seal
            or actual['actual_child_exit'] != 0 or actual['launcher_return_code'] != 0 or actual['inputs_unchanged'] is not True):
            raise ValueError('Successful exact first-build receipt and root-observed output identity required')
    fresh(run)
    env = os.environ.copy()
    removed = []
    for key in list(env):
        upper = key.upper()
        if (re.search('API_?KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|BASE_URL', upper)
            or upper.startswith(('ANTHROPIC_', 'OPENAI_', 'GOOGLE_API_', 'GEMINI_API_', 'XAI_', 'GROK_', 'CLAUDE_CODE_USE_'))
            or upper in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'PYTHONPATH', 'PYTHONHOME'}):
            removed.append(key)
            env.pop(key)
    env.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_DATASETS_OFFLINE='1', PYTHONDONTWRITEBYTECODE='1',
        SOURCE_DATE_EPOCH='1' if label == 'py314-01' else '2000000000', IG_FORBIDDEN_LIVE=r'C:\Users\hello\AppData\Local\Uoink\index.db')
    interpreter = Path(r'C:\Python314\python.exe') if label == 'py314-01' else RUNTIME / 'python.exe'
    child = OUT / ('build-guarded314.py' if label == 'py314-01' else 'build-guarded313.py')
    command = [str(interpreter), '-I', '-S', '-B', str(child), label, '--execute-reviewed-build']
    if label == 'py313-01':
        command += ['--comparison-sha256', comparison_sha, '--comparison-size', str(comparison_size)]
    write_json(run, 'launch-plan.json', {'command': command, 'cwd': str(OUT), 'manifest_sha256': seal,
        'source_date_epoch': env['SOURCE_DATE_EPOCH'], 'scrubbed_variable_names': sorted(removed),
        'runtime_plan_sha256': PLAN_HASH if label == 'py313-01' else None,
        'comparison_sha256': comparison_sha, 'comparison_size': comparison_size,
        'started_utc': datetime.now(timezone.utc).isoformat()})
    result = {'actual_child_exit': None, 'launcher_return_code': 1, 'inputs_unchanged': False,
              'runtime_unchanged': None if label == 'py314-01' else False}
    try:
        with (run / 'console.log').open('x', encoding='utf-8', newline='\n') as log:
            result['actual_child_exit'] = subprocess.run(command, cwd=OUT, env=env, stdout=log, stderr=subprocess.STDOUT).returncode
        verify_preparation(seal)
        result['inputs_unchanged'] = True
        if label == 'py313-01':
            verify_runtime(data)
            result['runtime_unchanged'] = True
        result['launcher_return_code'] = result['actual_child_exit']
    except Exception as exc:
        result['failure'] = {'type': type(exc).__name__, 'message': str(exc)}
        traceback.print_exc()
    result['finished_utc'] = datetime.now(timezone.utc).isoformat()
    write_json(run, 'launch-result.json', result)
    return result['launcher_return_code']

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('label', choices=('py314-01', 'py313-01'))
    parser.add_argument('--manifest-sha256', required=True)
    parser.add_argument('--comparison-sha256')
    parser.add_argument('--comparison-size', type=int)
    parser.add_argument('--execute-reviewed-build', action='store_true')
    args = parser.parse_args()
    if not args.execute_reviewed_build:
        print('Prepared only. No runtime, wheel, model or build accessed.')
        return 0
    if args.label == 'py313-01':
        if not re.fullmatch('[a-f0-9]{64}', args.comparison_sha256 or '') or not isinstance(args.comparison_size, int) or not 1 <= args.comparison_size <= 5 * 1024 * 1024:
            raise ValueError('Root-observed first wheel hash and bounded size required')
    elif args.comparison_sha256 is not None or args.comparison_size is not None:
        raise ValueError('First output identity is unknown before first build')
    verify_preparation(args.manifest_sha256)
    data = plan() if args.label == 'py313-01' else None
    return build(data, args.manifest_sha256, args.label, args.comparison_sha256, args.comparison_size)

if __name__ == '__main__':
    raise SystemExit(main())
