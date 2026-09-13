import ast
from pathlib import Path
root=Path(r'E:\AI\projects\uoink\checkouts\Yoink-library')
tree=root / '_scratch/wheel-integrator13'
path=tree / 'scripts/build_nltk_pathsec_wheel.py'
source=path.read_text(encoding='utf8')
def replace(old,new):
    global source
    assert source.count(old)==1,old[:80]
    source=source.replace(old,new)
replace('import base64','import base64\nimport csv\nimport email\nimport io')
replace('except (FileNotFoundError, PermissionError, OSError):','except FileNotFoundError:')
replace('    p = Path(path).absolute()\n    verify_no_links_or_reparse(p, "Hash input")','    p = safe_local_path(path)\n    verify_no_links_or_reparse(p, "Hash input")')
replace('''        if name in seen_names:
            raise ValueError(f"Duplicate member in archive: {name}")
        seen_names.add(name)''','''        if not name or "\\\\" in name or any(p in ("", ".", "..") for p in name.rstrip("/").split("/")):
            raise ValueError(f"Path traversal or ambiguous archive member: {name}")
        normalized = name.rstrip("/").casefold()
        if normalized in seen_names:
            raise ValueError(f"Duplicate member in archive: {name}")
        seen_names.add(normalized)''')
replace('''    record_lines = record_bytes.decode("utf-8").splitlines()
    record_entries: dict[str, tuple[str, int]] = {}

    for line in record_lines:
        if not line.strip():
            continue
        parts = line.split(",")''','''    record_lines = csv.reader(io.StringIO(record_bytes.decode("utf-8")), strict=True)
    record_entries: dict[str, tuple[str, int]] = {}
    seen_records = set()

    for parts in record_lines:
        line = repr(parts)''')
replace('''        entry_path, entry_hash, entry_size = parts[0], parts[1], parts[2]
        if entry_path == record_path:''','''        entry_path, entry_hash, entry_size = parts[0], parts[1], parts[2]
        if entry_path.casefold() in seen_records:
            raise ValueError('Duplicate RECORD entry: ' + entry_path)
        seen_records.add(entry_path.casefold())
        if entry_path == record_path:
            if entry_hash or entry_size:
                raise ValueError('RECORD self entry must have empty hash and size')''')
replace('''    # Verify every member in RECORD matches actual archive content''','''    if record_path.casefold() not in seen_records:
        raise ValueError('Missing RECORD self entry')

    # Verify every member in RECORD matches actual archive content''')
replace('''    metadata_text = archive.read(metadata_path).decode("utf-8")''','''    metadata_text = archive.read(metadata_path).decode("utf-8")
    parsed_meta = email.message_from_string(metadata_text)
    for header in ('Metadata-Version', 'Name', 'Version', 'Requires-Python'):
        if len(parsed_meta.get_all(header) or []) > 1:
            raise ValueError('Duplicate metadata singleton: ' + header)''')
replace('''    wheel_meta_text = archive.read(wheel_meta_path).decode("utf-8")''','''    wheel_meta_text = archive.read(wheel_meta_path).decode("utf-8")
    parsed_wheel = email.message_from_string(wheel_meta_text)
    if (parsed_wheel.get_all('Wheel-Version') != ['1.0'] or
            parsed_wheel.get_all('Root-Is-Purelib') != ['true'] or
            parsed_wheel.get_all('Tag') != ['py3-none-any']):
        raise ValueError('Malformed metadata: missing Wheel-Version 1.0 in WHEEL or incompatible wheel tags')''')
replace('''    # Invariant: NLTK must not be imported
    if "nltk" in sys.modules:
        raise RuntimeError("NLTK must not be imported in packaging utility")

''','')
replace('''    actual_size = raw_wheel.stat().st_size''','''    wheel_bytes = raw_wheel.read_bytes()
    actual_size = len(wheel_bytes)''')
replace('''    actual_sha256 = sha256_file(raw_wheel)''','''    actual_sha256 = hashlib.sha256(wheel_bytes).hexdigest()''')
replace('''    with zipfile.ZipFile(raw_wheel, "r") as archive:''','''    with zipfile.ZipFile(io.BytesIO(wheel_bytes), "r") as archive:''')
replace('''        repo_scratch = Path(__file__).resolve().parent.parent / "_scratch"
        scratch_dir = repo_scratch if repo_scratch.parent.is_dir() else out_dir.parent
        scratch_dir.mkdir(parents=True, exist_ok=True)
        tmp_base = scratch_dir / f".tmp_whl_build_{os.getpid()}_{int(time.time() * 1000)}"
        tmp_base.mkdir(parents=True, exist_ok=False)''','''        scratch_dir = safe_local_path(Path(__file__).absolute().parent.parent / '_scratch')
        scratch_dir.mkdir(parents=True, exist_ok=True)
        tmp_base = safe_local_path(scratch_dir / f'.tmp_whl_build_{os.getpid()}_{time.time_ns()}')
        assert tmp_base.parent == scratch_dir
        tmp_base.mkdir(exist_ok=False)''')
replace('''            # 9. Determine deterministic zip timestamp
            if "SOURCE_DATE_EPOCH" in os.environ:
                try:
                    epoch = int(os.environ["SOURCE_DATE_EPOCH"])
                    zip_time = time.gmtime(epoch)[:6]
                except ValueError:
                    zip_time = DEFAULT_ZIP_TIMESTAMP
            else:
                zip_time = DEFAULT_ZIP_TIMESTAMP''','''            # A fixed timestamp and stored entries avoid ambient epoch/zlib drift.
            zip_time = DEFAULT_ZIP_TIMESTAMP''')
source=source.replace('compression=zipfile.ZIP_DEFLATED','compression=zipfile.ZIP_STORED').replace('zinfo.compress_type = zipfile.ZIP_DEFLATED','zinfo.compress_type = zipfile.ZIP_STORED')
replace('''                    zinfo.external_attr = DEFAULT_FILE_MODE << 16''','''                    zinfo.create_system = 3
                    zinfo.external_attr = DEFAULT_FILE_MODE << 16''')
replace('''                "deterministic": True,''','''                "deterministic": True,
                "archive_format": "ZIP_STORED; fixed timestamp, sorted members and Unix file modes",
                "work_directory": str(tmp_base),
                "release_ready": False,''')
replace('''            shutil.rmtree(tmp_base, ignore_errors=True)''','''            # Preserve work on success or failure for review; no recursive cleanup.
            pass''')
ast.parse(source)
path.write_text(source,encoding='utf8',newline='\n')
print('Builder boundaries repaired in detached takeover only; tests/artifact unchanged.')
