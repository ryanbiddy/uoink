"""One exact already-built NLTK wheel, metadata only; no package import."""
from __future__ import annotations
import base64
import csv
import email.parser
import email.policy
import encodings.cp437
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import sys
import time
import zipfile
import zlib

ROOT = Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
BASE = ROOT / '_scratch/nltk-local-metadata-reader01'
ARTIFACT = ROOT / 'docs/library/proof/nltk-local-wheel-2026-09-13/final-artifact/nltk-3.10.3+uoink.pathsec1-py3-none-any.whl'
SIZE = 6597605
SHA = '969f623541344ade83ea267130e016d6cb8a223ecaaf28fb3d7a663c7e3c60d8'
PREFIX = 'nltk-3.10.3+uoink.pathsec1.dist-info/'
METADATA, RECORD = PREFIX + 'METADATA', PREFIX + 'RECORD'
OUT = BASE / 'results/read01'
TEXT_PINS = {
    'inputs/final-result.json': (793, '5c3b1c107b96a50b60f4630cd863807f71ef0a7a22306a8a7fa22d45e42a663f'),
    'inputs/final-provenance.json': (2389, 'a033900b7c76c745b0bb70716a9a5bd3b8e9a9d6d71b9234cead49cc3b07967d'),
    'inputs/original-proof-SHA256.json': (13189, '3617f8c00ba5aa40e84f427ae766dba018cf37a5235ef651bca03231e9269463'),
    'inputs/upstream-METADATA.txt': (3230, '78584b6194873a677ecc029634f2178e6b962fababd4188a0049d76e6b64ba1e'),
    'inputs/builder-source.txt': (25377, '0f1d4116f5aa7b733e562f2d911ccedcedd69f7824fdf7462d343f6aa1ecfb34'),
}
deadline = time.monotonic() + 30
violations = []
observations = []
reads = []

def require(value, message):
    if not value: raise ValueError(message)

def clock(): require(time.monotonic() <= deadline, 'Cooperative deadline exceeded')

def lexical(path):
    require(isinstance(path, (str, bytes, os.PathLike)), 'Descriptor path refused')
    return os.path.normcase(os.path.abspath(os.fsdecode(os.fspath(path))))

read_names = {lexical(BASE / name) for name in TEXT_PINS} | {lexical(ARTIFACT)}
write_names = {lexical(OUT / name) for name in ('nltk-local-METADATA.txt', 'receipt.json')}
directory_names = {lexical(BASE / 'results'), lexical(OUT)}

def audit(event, args):
    denied = False
    if event == 'open':
        path, mode, flags = args
        name = lexical(path)
        writing = (isinstance(mode, str) and any(c in mode for c in 'wax+')) or flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        denied = name not in (write_names if writing else read_names)
    elif event == 'os.mkdir': denied = lexical(args[0]) not in directory_names
    elif event.startswith(('socket.', 'subprocess.', 'ctypes.', 'winreg.')) or event in {
        'os.system','os.startfile','os.exec','os.posix_spawn','os.spawn','os.remove','os.rmdir',
        'os.rename','os.link','os.symlink','os.chdir','os.truncate','os.chmod','os.utime'}:
        denied = True
    if denied:
        violations.append(event)
        raise PermissionError('Outside exact NLTK metadata-reader scope: ' + event)

def chain(path, missing_leaf=False):
    # Only call with fixed inputs/outputs. No path comes from archive content.
    require(lexical(path) in read_names | write_names | directory_names, 'Unbound path')
    for component in reversed((path,) + tuple(path.parents)):
        try: info = os.lstat(component)
        except FileNotFoundError:
            require(component == path and missing_leaf, 'Missing ancestor/input')
            continue
        require(not stat.S_ISLNK(info.st_mode) and not getattr(info, 'st_file_attributes', 0) & 0x400, 'Reparse path refused')
        if component != path: require(stat.S_ISDIR(info.st_mode), 'Nondirectory ancestor')

def identity(info):
    fields = ('st_dev','st_ino','st_mode','st_nlink','st_size','st_mtime_ns','st_ctime_ns')
    result = {name: getattr(info, name) for name in fields}
    if hasattr(info, 'st_birthtime_ns'): result['st_birthtime_ns'] = info.st_birthtime_ns
    return result

def cross_identity(path_id, handle_id):
    # Windows path/handle ctime meanings differ in observed Python versions.
    # Keep full exact stability inside each API; cross-bind birthtime instead.
    keys = set(path_id) | set(handle_id)
    if os.name == 'nt':
        require('st_birthtime_ns' in path_id and 'st_birthtime_ns' in handle_id, 'Required Windows birthtime absent')
        keys.discard('st_ctime_ns')
    require(all(path_id.get(k) == handle_id.get(k) for k in keys), 'Path/handle identity mismatch')

def snapshot(path, expected_size, expected_sha):
    clock(); chain(path)
    before = identity(os.lstat(path))
    require(stat.S_ISREG(before['st_mode']) and before['st_size'] == expected_size, 'Expected regular file/size required')
    with path.open('rb') as stream:
        handle_before = identity(os.fstat(stream.fileno()))
        cross_identity(before, handle_before)
        raw = stream.read(expected_size + 1)
        handle_after = identity(os.fstat(stream.fileno()))
    chain(path)
    after = identity(os.lstat(path))
    require(before == after and handle_before == handle_after, 'Input changed during read')
    cross_identity(after, handle_after)
    require(len(raw) == expected_size and hashlib.sha256(raw).hexdigest() == expected_sha, 'Exact input hash/size mismatch')
    clock()
    reads.append({'path': str(path), 'bytes': len(raw), 'sha256': expected_sha,
                  'path_before': before, 'path_after': after, 'handle_before': handle_before, 'handle_after': handle_after})
    return raw

def unique_json(raw):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique)

def member_name(name):
    require(type(name) is str and name and '\\' not in name and ':' not in name and '\x00' not in name, 'Invalid member name')
    parts = name.split('/')
    require(not name.startswith('/') and all(p not in {'','.','..'} for p in parts), 'Noncanonical member path')
    require(PurePosixPath(name).as_posix() == name, 'Normalized member differs')
    require(name.isascii() and len(name) <= 512, 'Unexpected member name encoding/bounds')

def parse_exact_archive(raw):
    require(len(raw) == SIZE and hashlib.sha256(raw).hexdigest() == SHA, 'Artifact identity precedes ZIP parsing')
    require(raw[-22:-18] == b'PK\x05\x06', 'Exact uncommented EOCD required')
    sig, disk, cd_disk, disk_count, count, cd_size, cd_start, comment = struct.unpack('<IHHHHIIH', raw[-22:])
    require(disk == cd_disk == comment == 0 and disk_count == count == 512, 'Single-disk 512-member archive required')
    require(0 < cd_start < len(raw) - 22 and cd_start + cd_size == len(raw) - 22, 'Central directory bounds')
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        infos = archive.infolist()
        require(len(infos) == 512 and archive.start_dir == cd_start and not archive.comment, 'Directory identity')
        names = set(); folded = set(); position = 0
        for info in infos:
            clock(); member_name(info.filename)
            require(info.filename not in names and info.filename.casefold() not in folded, 'Duplicate/ambiguous member')
            names.add(info.filename); folded.add(info.filename.casefold())
            require(not info.is_dir() and info.create_system == 3 and stat.S_ISREG(info.external_attr >> 16), 'Regular Unix member required')
            require(info.compress_type == zipfile.ZIP_STORED and info.compress_size == info.file_size, 'Only stored payloads allowed')
            require(info.flag_bits == 0 and not info.extra and not info.comment and info.volume == 0, 'No flags/extras/comments/multidisk')
            require(0 <= info.file_size <= SIZE and info.header_offset == position, 'Bounded contiguous member layout')
            require(position + 30 <= cd_start, 'Local header crosses central directory')
            header = struct.unpack_from('<IHHHHHIIIHH', raw, position)
            hsig, needed, flags, method, tm, dt, crc, comp, size, name_len, extra_len = header
            require(hsig == 0x04034B50 and flags == info.flag_bits and method == 0 and extra_len == 0, 'Local header mismatch')
            require((crc, comp, size) == (info.CRC, info.compress_size, info.file_size), 'Local size/CRC disagreement')
            start = position + 30 + name_len
            require(start <= cd_start and raw[position+30:start] == info.filename.encode('ascii'), 'Local filename mismatch')
            position = start + size
            require(position <= cd_start, 'Overlapping/outside payload extent')
        require(position == cd_start and METADATA in names and RECORD in names, 'Final extent/selected membership')
        meta_info, rec_info = archive.getinfo(METADATA), archive.getinfo(RECORD)
        require(0 < meta_info.file_size <= 65536 and 0 < rec_info.file_size <= 262144, 'Selected text bounds')
        metadata, record = archive.read(meta_info), archive.read(rec_info)
        require(zlib.crc32(metadata) & 0xffffffff == meta_info.CRC and zlib.crc32(record) & 0xffffffff == rec_info.CRC, 'Selected CRC mismatch')
        # No other payload is read through ZipFile. Whole-file hashing above was opaque.
        records = {}
        for row in csv.reader(io.StringIO(record.decode('utf-8', 'strict'), newline='')):
            require(len(row) == 3, 'RECORD column count')
            name, digest, length = row
            require(name in names and name not in records, 'RECORD duplicate/unknown member')
            if name == RECORD: require(digest == length == '', 'RECORD self row must be unhashed')
            else:
                require(re.fullmatch(r'sha256=[A-Za-z0-9_-]{43}', digest) is not None and re.fullmatch(r'0|[1-9][0-9]{0,8}', length) is not None, 'RECORD digest/size syntax')
                require(int(length) == archive.getinfo(name).file_size, 'RECORD/central size mismatch')
            records[name] = (digest, length)
        require(set(records) == names, 'Complete RECORD membership required')
        digest = 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(metadata).digest()).rstrip(b'=').decode('ascii')
        require(records[METADATA] == (digest, str(len(metadata))), 'Selected METADATA RECORD hash/size mismatch')
        return metadata, {'members': len(infos), 'record_rows': len(records), 'record_bytes': len(record),
                          'record_sha256': hashlib.sha256(record).hexdigest(), 'selected_members_read': [METADATA, RECORD],
                          'other_payload_record_hashes_recomputed': False, 'whole_file_hash_verified': True}

def metadata_fields(raw, version):
    text = raw.decode('utf-8', 'strict')
    message = email.parser.Parser(policy=email.policy.default).parsestr(text)
    require(not message.defects, 'METADATA parser defects')
    for field in ('Metadata-Version','Name','Version','Requires-Python'):
        require(len(message.get_all(field, [])) == 1, 'METADATA singleton missing/duplicate: ' + field)
    require(str(message['Name']) == 'nltk' and str(message['Version']) == version, 'METADATA identity mismatch')
    return {'name': str(message['Name']), 'version': str(message['Version']),
            'requires_python': str(message['Requires-Python']),
            'requires_dist': [str(value) for value in message.get_all('Requires-Dist', [])],
            'provides_extra': [str(value) for value in message.get_all('Provides-Extra', [])]}

def write_new(path, raw):
    require(lexical(path) in write_names and len(raw) <= 131072, 'Output scope/bound')
    chain(path, missing_leaf=True)
    with path.open('xb') as stream: stream.write(raw); stream.flush(); os.fsync(stream.fileno())

def main():
    started = time.monotonic()
    require(os.environ.get('IG_FORBIDDEN_LIVE') == r'C:\Users\hello\AppData\Local\Uoink\index.db', 'Required startup binding')
    require(os.environ.get('TORCH_DEVICE_BACKEND_AUTOLOAD') == '0', 'Autoload must be disabled')
    require(sys.flags.isolated and sys.flags.no_site and sys.dont_write_bytecode and len(sys.argv) == 1, 'Isolated exact invocation required')
    sys.addaudithook(audit)
    # Fresh fixed output directories only. Existing read01 refuses without writes.
    parent = BASE / 'results'
    chain(parent, missing_leaf=True)
    parent.mkdir(exist_ok=True)
    chain(OUT, missing_leaf=True)
    OUT.mkdir(exist_ok=False)
    receipt = {'status': 'REFUSED', 'exit': 2, 'artifact_verified_in_this_invocation': False,
               'artifact_origin': 'owned-built-wheel', 'public_local_release_record': False,
               'artifact_url': None, 'wheel_member_imports': False, 'model_execution': False, 'runtime_accepted': False}
    exit_code = 2
    try:
        texts = {name: snapshot(BASE / name, *pin) for name, pin in TEXT_PINS.items()}
        provenance = unique_json(texts['inputs/final-provenance.json'])
        previous = unique_json(texts['inputs/final-result.json'])
        original_manifest = unique_json(texts['inputs/original-proof-SHA256.json'])
        require(provenance['output_wheel'] == {'filename': ARTIFACT.name, 'sha256': SHA, 'size': SIZE}, 'Accepted artifact provenance mismatch')
        require(previous['wheel_sha256'] == SHA and previous['wheel_bytes'] == SIZE and previous['members'] == 512, 'Prior independent artifact binding mismatch')
        require(original_manifest['final-artifact/' + ARTIFACT.name] == SHA, 'Original proof artifact hash mismatch')
        raw = snapshot(ARTIFACT, SIZE, SHA)
        receipt['artifact_verified_in_this_invocation'] = True
        metadata, archive = parse_exact_archive(raw)
        upstream = texts['inputs/upstream-METADATA.txt']
        expected, changes = re.subn(r'^Version:\s*3\.10\.3\s*$', 'Version: 3.10.3+uoink.pathsec1', upstream.decode('utf-8'), flags=re.MULTILINE)
        require(changes == 1 and expected.encode('utf-8') == metadata, 'Exact reviewed Version-only METADATA transformation mismatch')
        local_fields = metadata_fields(metadata, '3.10.3+uoink.pathsec1')
        public_fields = metadata_fields(upstream, '3.10.3')
        require(all(local_fields[k] == public_fields[k] for k in ('name','requires_python','requires_dist','provides_extra')), 'Unexpected dependency/Python metadata change')
        clock(); require(not violations, 'Scope guard violation')
        write_new(OUT / 'nltk-local-METADATA.txt', metadata)
        clock()
        receipt.update(status='PASS', exit=0, metadata_bytes=len(metadata), metadata_sha256=hashlib.sha256(metadata).hexdigest(),
                       fields=local_fields, archive=archive, exact_version_only_transformation=True,
                       artifact={'filename': ARTIFACT.name, 'bytes': SIZE, 'sha256': SHA})
        exit_code = 0
    except Exception as exc:
        receipt.update(error_type=type(exc).__name__, error=str(exc))
    receipt.update(reads=reads, guard_violations=violations, elapsed_seconds=time.monotonic()-started,
                   scope='Exact local packaging METADATA receipt; no installation, graph acceptance or model qualification.')
    encoded = json.dumps(receipt, indent=2).encode() + b'\n'
    if receipt['exit'] == 0 and time.monotonic() > deadline:
        receipt.update(status='REFUSED', exit=2, error_type='DeadlineRefusal', error='Deadline crossed before receipt publication')
        encoded = json.dumps(receipt, indent=2).encode() + b'\n'
        exit_code = 2
    write_new(OUT / 'receipt.json', encoded)
    print(json.dumps({k: receipt[k] for k in ('status','exit','artifact_verified_in_this_invocation','elapsed_seconds')}))
    return exit_code

if __name__ == '__main__': raise SystemExit(main())
