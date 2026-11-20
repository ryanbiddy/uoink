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
without a call. The safetensors file is read with numpy (it is a JSON header
plus raw little-endian floats), so the only other dependency is the
``tokenizers`` package that already ships for transcription.
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

_lock = threading.RLock()
_model: dict | None = None
_last_used = 0.0
_timer: threading.Timer | None = None


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
        for name in (WEIGHTS_FILE, TOKENIZER_FILE):
            path = folder / name
            if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
                return None
    except OSError:
        return None
    return folder


def is_available() -> bool:
    if model_dir() is None:
        return False
    try:
        import numpy  # noqa: F401
        import tokenizers  # noqa: F401
    except Exception:
        return False
    return True


def _read_matrix(path: Path):
    import numpy as np
    dtypes = {"F32": "<f4", "F16": "<f2", "BF16": None}
    with path.open("rb") as stream:
        size = int.from_bytes(stream.read(8), "little")
        if not 0 < size <= _MAX_HEADER:
            raise EmbedUnavailable("weights header is not valid")
        header = json.loads(stream.read(size).decode("utf-8"))
    tensors = {k: v for k, v in header.items() if k != "__metadata__" and isinstance(v, dict)}
    meta = tensors.get("embeddings") or (next(iter(tensors.values())) if len(tensors) == 1 else None)
    if not meta or len(meta.get("shape") or []) != 2 or dtypes.get(meta.get("dtype")) is None:
        raise EmbedUnavailable("weights need one 2-D float tensor named embeddings")
    rows, dim = (int(v) for v in meta["shape"])
    start, end = (int(v) for v in meta["data_offsets"])
    dtype = np.dtype(dtypes[meta["dtype"]])
    if end - start != rows * dim * dtype.itemsize or 8 + size + end > path.stat().st_size:
        raise EmbedUnavailable("weights size does not match the header")
    matrix = np.fromfile(path, dtype=dtype, count=rows * dim, offset=8 + size + start)
    return matrix.reshape(rows, dim).astype(np.float32)


def _load() -> dict:
    global _model
    if _model is not None:
        return _model
    folder = model_dir()
    if folder is None or not is_available():
        raise EmbedUnavailable("the bundled embedding model is not installed")
    from tokenizers import Tokenizer
    tokenizer = Tokenizer.from_file(str(folder / TOKENIZER_FILE))
    unk = None
    try:
        unk_token = getattr(tokenizer.model, "unk_token", None)
        unk = tokenizer.token_to_id(unk_token) if unk_token else None
    except Exception:
        unk = None
    _model = {"matrix": _read_matrix(folder / WEIGHTS_FILE), "tokenizer": tokenizer, "unk": unk}
    return _model


def _touch() -> None:
    global _last_used, _timer
    _last_used = time.monotonic()
    if _timer is None:
        _timer = threading.Timer(IDLE_SECONDS, _idle_check)
        _timer.daemon = True
        _timer.start()


def _idle_check() -> None:
    global _timer
    with _lock:
        _timer = None
        if _model is None:
            return
        if time.monotonic() - _last_used >= IDLE_SECONDS:
            release()
        else:
            _touch()


def release() -> None:
    """Drop the loaded model; the next call loads it again."""
    global _model
    with _lock:
        _model = None


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
