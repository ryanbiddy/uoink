"""Qualify patched Python imports and instantiator checks, without unpickling."""
import datetime as dt
import hashlib
import importlib
import json
import os
from pathlib import Path
import sys
import traceback
import zipfile

r = Path(__file__).resolve().parents[1]
out = r / '_scratch/lightning266-runtime-01'
out.mkdir(exist_ok=False)
overlay = out / 'overlay'
overlay.mkdir()
events = []
def audit(event, args):
    if event in ('socket.connect', 'socket.bind', 'socket.sendto', 'socket.getaddrinfo', 'subprocess.Popen'):
        events.append(event)
        raise PermissionError('Qualification refuses network and subprocesses')
    if event in ('open', 'sqlite3.connect') and args and isinstance(args[0], (str, bytes, os.PathLike)):
        name = os.fsdecode(args[0]).replace('\\', '/').lower()
        if 'c:/users/hello/appdata/local/uoink/index.db' in name:
            events.append(event)
            raise PermissionError('Ordinary index prohibited')
sys.addaudithook(audit)
for name in ('lightning', 'pytorch-lightning'):
    metadata = json.loads((r / f'_scratch/dependency-closure-astra-01/{name}.json').read_text(encoding='utf8'))
    row = next(x for x in metadata['urls'] if x['packagetype'] == 'bdist_wheel')
    wheel = r / '_scratch/dependency-closure-astra-01' / row['filename']
    assert hashlib.sha256(wheel.read_bytes()).hexdigest() == row['digests']['sha256']
    with zipfile.ZipFile(wheel) as archive:
        for member in archive.infolist():
            target = overlay / member.filename
            assert target.resolve().is_relative_to(overlay.resolve())
        archive.extractall(overlay)
sys.path[:0] = [str(overlay), str(r / 'installer/staging')]
rows = []
def check(name, operation):
    try:
        detail = operation()
        rows.append({'name': name, 'status': 'passed', 'detail': detail})
    except Exception:
        rows.append({'name': name, 'status': 'failed', 'traceback': traceback.format_exc()})
    (out / 'results.json').write_text(json.dumps(rows, indent=2) + '\n', encoding='utf8')
    (out / 'guard-events.json').write_text(json.dumps(events) + '\n', encoding='utf8')

def probe(namespace):
    lib = importlib.import_module(namespace)
    assert lib.__version__ == '2.6.6'
    assert Path(lib.__file__).is_relative_to(overlay)
    saving = importlib.import_module(namespace + '.core.saving')
    class FixtureData(lib.LightningDataModule):
        pass
    valid = saving._load_state(FixtureData, {})
    assert isinstance(valid, FixtureData)
    key = FixtureData.CHECKPOINT_HYPER_PARAMS_KEY
    for params, phrase in [
        ({'_instantiator': 'os.system'}, 'allowlist'),
        ({'_instantiator': next(iter(saving._ALLOWED_INSTANTIATORS)),
          '_class_path': 'os.system'}, 'already imported'),
    ]:
        try:
            saving._load_state(FixtureData, {key: params})
        except ValueError as exc:
            assert phrase in str(exc), str(exc)
        else:
            raise AssertionError('Untrusted instantiation accepted')
    return {'version': lib.__version__, 'benign_data_module': True,
            'untrusted_instantiator_refused': True, 'unimported_class_refused': True,
            'file': lib.__file__}

check('lightning.pytorch patched instantiation', lambda: probe('lightning.pytorch'))
check('pytorch_lightning patched instantiation', lambda: probe('pytorch_lightning'))
def imports():
    import whisper_runner
    import whisperx
    from pyannote.audio.core.model import Model
    from whisperx.vads.pyannote import load_vad_model
    assert callable(Model.from_pretrained) and callable(load_vad_model)
    return {'whisperx': whisperx.__file__, 'checkpoint_loaded': False,
            'decoder_directory_registered': whisper_runner._PACKAGED_DECODER_DLL_HANDLE is not None}
check('WhisperX and PyAnnote imports', imports)
summary = {'python': sys.version, 'executable': sys.executable,
           'passed': sum(x['status'] == 'passed' for x in rows),
           'failed': sum(x['status'] == 'failed' for x in rows),
           'network_or_subprocess_guard_events': events, 'checkpoint_loaded': False,
           'model_inference': False, 'finished_utc': dt.datetime.now(dt.timezone.utc).isoformat()}
(out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf8')
print(json.dumps(summary, indent=2))
raise SystemExit(int(summary['failed'] > 0))
