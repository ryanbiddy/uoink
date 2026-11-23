"""Small text embeddings on this computer, from a bundled static model (3.18).

Uoink ships minishlab/potion-base-8M (MIT, about 30 MB): a table with one
256-number vector per word piece. Embedding a text is tokenize, look up the
rows, average them and scale to unit length. Nothing neural runs, there is no
network and no GPU, and a few thousand texts take well under a second.

Weights live at ``<app>/models/embed-bundled/potion-base-8m/`` ({app} on
Windows, Contents/Resources in the macOS bundle), staged by the build from
``scripts/embed_model_pin.json``. ``UOINK_EMBED_MODEL_DIR`` points at another
folder (tests, source checkouts). When the weights are absent
``is_available()`` is False and callers use their non-embedding path.

The model loads on first use and is dropped again after ``IDLE_SECONDS``
without a call. Before the first load in a process both files are checked
against the pinned sha256 (``PINNED_SHA256``, the same values as the pin
file), and checked again only when their size or modified time changes. A
file that fails the check or does not parse makes the model unavailable for
that file version, so captures fall back to words instead of retrying. The
safetensors file is read with numpy (a JSON header plus raw little-endian
floats), every header field checked against the file's real size, so the
only other dependency is the ``tokenizers`` package that already ships for
transcription.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

MODEL_NAME = "potion-base-8m"
BUNDLED_DIRNAME = "embed-bundled"
ENV_DIR = "UOINK_EMBED_MODEL_DIR"
WEIGHTS_FILE = "model.safetensors"
TOKENIZER_FILE = "tokenizer.json"
IDLE_SECONDS = 600
MAX_TOKENS = 512
MAX_CHARS = 6000
_MAX_HEADER = 1 << 20
MAX_WEIGHT_BYTES = 256 << 20
# scripts/embed_model_pin.json; tests/test_stage_embed_model.py keeps them equal.
PINNED_SHA256 = {
    WEIGHTS_FILE: "f65d0f325faadc1e121c319e2faa41170d3fa07d8c89abd48ca5358d9a223de2",
    TOKENIZER_FILE: "e67e803f624fb4d67dea1c730d06e1067e1b14d830e2c2202569e3ef0f70bb50",
}

_lock = threading.RLock()
_model: dict | None = None
_last_used = 0.0
_timer: threading.Timer | None = None
_verified: set = set()
_failed: dict = {}
_release_hooks: list = []


class EmbedUnavailable(RuntimeError):
    """No usable weights, or numpy/tokenizers are missing."""


def bundled_root() -> Path:
    """This install's bundled embedding folder (it may not exist)."""
    app_dir = None
    try:
        import uoink_install_isolation
        binding = uoink_install_isolation.current_binding()
        if binding is not None and binding.app_dir is not None:
            app_dir = Path(binding.app_dir)
    except Exception:  # pragma: no cover - the isolation module always ships
        app_dir = None
    if app_dir is None:
        app_dir = Path(__file__).resolve().parent
    elif app_dir.suffix == ".app":
        app_dir = app_dir / "Contents" / "Resources"
    return app_dir / "models" / BUNDLED_DIRNAME


def model_dir() -> Path | None:
    """The folder holding the weights and tokenizer, or None."""
    override = os.environ.get(ENV_DIR, "").strip()
    folder = Path(override) if override else bundled_root() / MODEL_NAME
    try:
        if folder.is_symlink() or not folder.is_dir():
            return None
        for name in (WEIGHTS_FILE, TOKENIZER_FILE):
            path = folder / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                return None
    except OSError:
        return None
    return folder


def identity() -> tuple | None:
    """Which weights are installed: the folder plus each file's size and
    modified time. None when there are none."""
    folder = model_dir()
    if folder is None:
        return None
    try:
        stats = [(folder / name).stat() for name in (WEIGHTS_FILE, TOKENIZER_FILE)]
    except OSError:
        return None
    return (str(folder),) + tuple((s.st_size, s.st_mtime_ns) for s in stats)


def is_available() -> bool:
    key = identity()
    if key is None or key in _failed:
        return False
    try:
        import numpy  # noqa: F401
        import tokenizers  # noqa: F401
    except Exception:
        return False
    return True


def _sha256(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _verify(folder: Path, key: tuple) -> None:
    """Both files match the pin. Hashed once per file version per process."""
    if key in _verified:
        return
    for name, expected in PINNED_SHA256.items():
        if _sha256(folder / name) != expected:
            raise EmbedUnavailable(f"{name} does not match the pinned sha256")
    _verified.add(key)


def _read_matrix(path: Path):
    """The embedding table, after checking every header field against the
    file. Any problem raises EmbedUnavailable."""
    import numpy as np
    dtypes = {"F32": "<f4", "F16": "<f2"}
    total = path.stat().st_size
    with path.open("rb") as stream:
        head = stream.read(8)
        if len(head) != 8:
            raise EmbedUnavailable("weights file is too short")
        size = int.from_bytes(head, "little")
        if not 0 < size <= _MAX_HEADER or 8 + size > total:
            raise EmbedUnavailable("weights header is not valid")
        raw = stream.read(size)
    try:
        header = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise EmbedUnavailable("weights header is not valid") from exc
    if not isinstance(header, dict):
        raise EmbedUnavailable("weights header is not valid")
    tensors = {k: v for k, v in header.items() if k != "__metadata__" and isinstance(v, dict)}
    meta = tensors.get("embeddings") or (next(iter(tensors.values())) if len(tensors) == 1 else None)
    shape = meta.get("shape") if isinstance(meta, dict) else None
    offsets = meta.get("data_offsets") if isinstance(meta, dict) else None
    if (not isinstance(shape, list) or len(shape) != 2 or meta.get("dtype") not in dtypes
            or not isinstance(offsets, list) or len(offsets) != 2
            or not all(type(v) is int for v in shape + offsets)):
        raise EmbedUnavailable("weights need one 2-D float tensor named embeddings")
    rows, dim = shape
    start, end = offsets
    dtype = np.dtype(dtypes[meta["dtype"]])
    if rows <= 0 or dim <= 0 or not 0 <= start < end:
        raise EmbedUnavailable("weights header is not valid")
    if (end - start != rows * dim * dtype.itemsize or end - start > MAX_WEIGHT_BYTES
            or 8 + size + end > total):
        raise EmbedUnavailable("weights size does not match the header")
    matrix = np.fromfile(path, dtype=dtype, count=rows * dim, offset=8 + size + start)
    if matrix.size != rows * dim:
        raise EmbedUnavailable("weights file is too short")
    matrix = matrix.reshape(rows, dim).astype(np.float32, copy=False)
    if not np.isfinite(matrix).all():
        raise EmbedUnavailable("weights hold values that are not numbers")
    return matrix


def _load() -> dict:
    global _model
    key = identity()
    if _model is not None and _model["key"] == key:
        return _model
    _model = None
    if key is None or not is_available():
        raise EmbedUnavailable("the bundled embedding model is not installed")
    folder = Path(key[0])
    try:
        _verify(folder, key)
        from tokenizers import Tokenizer
        tokenizer = Tokenizer.from_file(str(folder / TOKENIZER_FILE))
        unk = None
        try:
            unk_token = getattr(tokenizer.model, "unk_token", None)
            unk = tokenizer.token_to_id(unk_token) if unk_token else None
        except Exception:
            unk = None
        matrix = _read_matrix(folder / WEIGHTS_FILE)
    except Exception as exc:
        # Remember the bad file version so every capture does not re-read it.
        _failed[key] = str(exc)[:200]
        if isinstance(exc, EmbedUnavailable):
            raise
        raise EmbedUnavailable(f"the embedding model could not be read: {type(exc).__name__}") from exc
    _model = {"key": key, "matrix": matrix, "tokenizer": tokenizer, "unk": unk}
    return _model


def on_release(hook) -> None:
    """Call hook() whenever the model is dropped (idle or release())."""
    with _lock:
        if hook not in _release_hooks:
            _release_hooks.append(hook)


def _touch() -> None:
    global _last_used
    _last_used = time.monotonic()
    if _timer is None:
        _schedule(IDLE_SECONDS)


def _schedule(seconds: float) -> None:
    global _timer
    _timer = threading.Timer(max(1.0, seconds), _idle_check)
    _timer.daemon = True
    _timer.start()


def _idle_check() -> None:
    """Drop the model once it has sat unused for IDLE_SECONDS. A call in
    between moves the deadline; the check waits only for what is left."""
    global _timer
    with _lock:
        _timer = None
        if _model is None:
            return
        idle = time.monotonic() - _last_used
        if idle >= IDLE_SECONDS:
            release()
        else:
            _schedule(IDLE_SECONDS - idle)


def release() -> None:
    """Drop the loaded model; the next call loads it again."""
    global _model, _timer
    with _lock:
        _model = None
        if _timer is not None:
            _timer.cancel()
            _timer = None
        hooks = list(_release_hooks)
    for hook in hooks:
        try:
            hook()
        except Exception:  # pragma: no cover -- a cache hook never blocks a release
            pass


def is_loaded() -> bool:
    return _model is not None


def dimension() -> int:
    with _lock:
        return int(_load()["matrix"].shape[1])


def embed(texts):
    """Unit vectors, one row per text (float32, shape (n, dim)). A text with
    no known word pieces gets a row of zeros. Raises EmbedUnavailable."""
    import numpy as np
    texts = [str(t or "")[:MAX_CHARS] for t in texts]
    with _lock:
        model = _load()
        _touch()
        matrix, unk = model["matrix"], model["unk"]
        encodings = model["tokenizer"].encode_batch(texts, add_special_tokens=False)
    out = np.zeros((len(texts), matrix.shape[1]), dtype=np.float32)
    for row, encoding in enumerate(encodings):
        ids = [i for i in encoding.ids if i != unk and 0 <= i < matrix.shape[0]][:MAX_TOKENS]
        if ids:
            vector = matrix[ids].mean(axis=0)
            norm = float(np.linalg.norm(vector))
            if norm > 1e-12:
                out[row] = vector / norm
    return out


def status() -> dict:
    return {"model": MODEL_NAME, "available": is_available(), "loaded": is_loaded()}
