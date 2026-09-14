"""Worker-local owned ASR engine proposal; connects namespace, factory VAD, and owner.

This is source authoring only: no native execution, no subprocess, no model loading at import.
D3 acquisition and D4 actual native stack admission remain separate gates.
"""
from dataclasses import dataclass
from types import MappingProxyType
from typing import Optional, Union

FOUR = frozenset(("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"))
FIVE = frozenset(("config.json", "model.bin", "preprocessor_config.json", "tokenizer.json", "vocabulary.json"))

FOUR_FILE_MODELS = frozenset(("tiny", "base", "small", "medium"))
FIVE_FILE_MODELS = frozenset(("large", "large-v3-turbo"))

FEATURE_EXTRACTOR_DEFAULTS = MappingProxyType({
    "feature_size": 80,
    "sampling_rate": 16000,
    "hop_length": 160,
    "chunk_length": 30,
    "n_fft": 400,
})

COMPANION_DELTA_B3_NO_PATH = (
    "In B3 WhisperModel._get_feature_kwargs (B2.py:741), when preprocessor_bytes is None "
    "and files is provided, B3 probes os.path.isfile(config_path). Companion delta must guard "
    "with 'not files and os.path.isfile' or return captured feature extractor defaults without probing filesystem."
)


class EngineRefusal(RuntimeError):
    pass


def _require(condition, reason):
    if not condition:
        raise EngineRefusal(reason)


@dataclass(frozen=True, slots=True)
class _EngineConstructionPolicy:
    """Fixed CPU/options construction policy record.

    Missing values refuse instead of selecting auto or library defaults.
    Facade beam_size and best_of constraint is fixed to 1.
    """
    device: str = "cpu"
    device_index: int = 0
    compute_type: str = "int8"
    cpu_threads: int = 4
    num_workers: int = 1
    language: Optional[str] = None
    task: str = "transcribe"
    beam_size: int = 1
    best_of: int = 1
    patience: float = 1.0
    length_penalty: float = 1.0
    repetition_penalty: float = 1.0
    no_repeat_ngram_size: int = 0
    chunk_size: int = 30
    vad_onset: float = 0.500
    vad_offset: float = 0.363

    def __post_init__(self):
        _require(self.device == "cpu", "device_policy_cpu_required")
        _require(self.compute_type in ("int8", "float32"), "compute_type_policy_required")
        _require(self.device_index == 0, "device_index_zero_required")
        _require(isinstance(self.cpu_threads, int) and self.cpu_threads > 0, "cpu_threads_positive_int_required")
        _require(isinstance(self.num_workers, int) and self.num_workers > 0, "num_workers_positive_int_required")
        _require(self.beam_size == 1 and self.best_of == 1, "beam_and_best_of_one_required")
        _require(self.task in ("transcribe", "translate"), "valid_task_required")


class OwnedASREngine:
    """Worker-owned ASR engine identity wrapping the private constructed pipeline.

    Retains references to the underlying pipeline, model, VAD product, admitted namespace lease,
    and runtime owner generation. Does not expose bare models to callers.
    """
    __slots__ = ('_owner', '_pipeline', '_model', '_vad', '_namespace_lease', '_generation', '_active')

    def __init__(self, owner, pipeline, model, vad, namespace_lease, generation):
        self._owner = owner
        self._pipeline = pipeline
        self._model = model
        self._vad = vad
        self._namespace_lease = namespace_lease
        self._generation = generation
        self._active = True

    @property
    def pipeline(self):
        self.assert_bound()
        return self._pipeline

    @property
    def model(self):
        self.assert_bound()
        return self._model

    @property
    def vad(self):
        self.assert_bound()
        return self._vad

    @property
    def namespace_lease(self):
        self.assert_bound()
        return self._namespace_lease

    @property
    def generation(self):
        return self._generation

    @property
    def active(self):
        return self._active and getattr(self._owner, '_active', False)

    def assert_bound(self):
        _require(self._active is True, "engine_ownership_revoked")
        _require(self._generation is self._owner._generation, "engine_generation_mismatch")
        _require(getattr(self._owner, '_active', False), "owner_not_active")
        self._owner.assert_admitted_namespace_binding(self._namespace_lease)
        self._owner.assert_vad_binding(self._vad)


def execute_admitted_construction(
    attempt,
    policy: _EngineConstructionPolicy,
    whisper_model_cls=None,
    tokenizer_cls=None,
    options_cls=None,
    pipeline_cls=None,
) -> OwnedASREngine:
    """Execute admitted engine construction within an active single owner operation.

    Enforces:
    - Running within the serial owner operation ('engine' phase)
    - Admitted namespace lease binding and active read set
    - Registered owned VAD identity (pipeline field is 'vad_model')
    - Four-file schema refusal before any path service
    - Nonempty tokenizer and preprocessor bytes; filesystem/Hub fallback refused
    - Fresh 5-file dictionary forwarding into B3 constructor; retained namespace survives pops
    - Step-by-step object retention on attempt before subsequent constructor calls
    - Fixed CPU/options policy (device='cpu', compute_type in ('int8', 'float32'), beam/best_of=1)
    - Publication under owner lock verifying pipeline and VAD links
    """
    _require(attempt is not None and getattr(attempt, 'active', False), "active_attempt_required")
    owner = attempt.owner
    _require(owner is not None and getattr(owner, '_active', False), "active_owner_required")

    namespace_lease = attempt.namespace
    _require(namespace_lease is not None and getattr(namespace_lease, 'active', False), "active_namespace_lease_required")
    _require(namespace_lease.owner is owner and namespace_lease.generation is attempt.generation,
             "namespace_lease_owner_and_generation_binding")

    product = attempt.product
    _require(product is not None and getattr(product, 'active', False), "active_vad_product_required")
    vad = product.vad
    _require(vad is not None, "vad_model_required")

    # Policy validation
    _require(policy is not None, "engine_construction_policy_required")
    _require(policy.device == "cpu", "device_policy_cpu_required")
    _require(policy.compute_type in ("int8", "float32"), "compute_type_policy_required")
    _require(policy.device_index == 0, "device_index_zero_required")
    _require(isinstance(policy.cpu_threads, int) and policy.cpu_threads > 0, "cpu_threads_positive_int_required")
    _require(isinstance(policy.num_workers, int) and policy.num_workers > 0, "num_workers_positive_int_required")
    _require(policy.beam_size == 1 and policy.best_of == 1, "beam_and_best_of_one_required")

    # Check namespace buffers
    pinned = namespace_lease.pinned_namespace
    _require(pinned is not None and getattr(pinned, '_ready', False), "materialized_pinned_namespace_required")
    buffers = namespace_lease.buffers
    _require(type(buffers) is MappingProxyType, "immutable_namespace_buffers_required")

    names = frozenset(buffers.keys())
    _require(names in (FOUR, FIVE), "schema_must_be_four_or_five_files")

    # Require tokenizer bytes and refuse filesystem/Hub fallback
    _require("tokenizer.json" in buffers, "tokenizer_bytes_required")
    tokenizer_bytes = buffers["tokenizer.json"]
    _require(isinstance(tokenizer_bytes, bytes) and len(tokenizer_bytes) > 0, "nonempty_tokenizer_bytes_required")

    # Four-file models refused: absent or empty preprocessor reaches B3's filesystem fallback
    if "preprocessor_config.json" not in buffers:
        raise EngineRefusal("four_file_models_refused_absent_preprocessor")

    preprocessor_bytes = buffers["preprocessor_config.json"]
    _require(isinstance(preprocessor_bytes, bytes) and len(preprocessor_bytes) > 0,
             "nonempty_preprocessor_bytes_required")

    # Forward a fresh files map into constructor; immutable source namespace survives dictionary pops
    fresh_files = pinned.fresh_files_map()
    _require(fresh_files is not buffers, "files_map_must_be_fresh_copy")
    _require(fresh_files == dict(buffers), "fresh_files_match_buffers")

    # Bind exact classes if not supplied
    if whisper_model_cls is None:
        from whisperx.asr import WhisperModel
        whisper_model_cls = WhisperModel
    if tokenizer_cls is None:
        from faster_whisper.tokenizer import Tokenizer
        tokenizer_cls = Tokenizer
    if options_cls is None:
        from faster_whisper.transcribe import TranscriptionOptions
        options_cls = TranscriptionOptions
    if pipeline_cls is None:
        from whisperx.asr import FasterWhisperPipeline
        pipeline_cls = FasterWhisperPipeline

    model_id = namespace_lease.label

    # Step 1: Model constructor
    model = whisper_model_cls(
        model_id,
        device="cpu",
        device_index=0,
        compute_type=policy.compute_type,
        download_root=None,
        local_files_only=True,
        files=fresh_files,
        cpu_threads=policy.cpu_threads,
        num_workers=policy.num_workers,
        use_auth_token=None,
    )

    # Step 2: Retain model immediately before next fallible step
    owner._retain_admitted_engine_model(attempt, model)
    owner._check_admitted_engine_model_ready(attempt)

    # Step 3: Tokenizer constructor
    if policy.language is not None:
        multilingual = getattr(getattr(model, "model", None), "is_multilingual", True)
        tokenizer = tokenizer_cls(model.hf_tokenizer, multilingual, task=policy.task, language=policy.language)
    else:
        tokenizer = None

    # Step 4: Retain tokenizer immediately
    owner._retain_admitted_engine_tokenizer(attempt, tokenizer)

    # Step 5: Options & Pipeline constructor
    options = options_cls(
        beam_size=policy.beam_size,
        best_of=policy.best_of,
        patience=policy.patience,
        length_penalty=policy.length_penalty,
        repetition_penalty=policy.repetition_penalty,
        no_repeat_ngram_size=policy.no_repeat_ngram_size,
        without_timestamps=True,
    )
    vad_params = {
        "chunk_size": policy.chunk_size,
        "vad_onset": policy.vad_onset,
        "vad_offset": policy.vad_offset,
    }
    pipeline = pipeline_cls(
        model=model,
        vad=vad,
        options=options,
        tokenizer=tokenizer,
        language=policy.language,
        vad_params=vad_params,
    )
    pipeline.model_path = model_id

    # Step 6: Retain pipeline immediately
    owner._retain_admitted_engine_pipeline(attempt, pipeline)

    # Step 7: Verify immutable namespace survived constructor dictionary pops
    _require(len(pinned.buffers) == 5, "namespace_buffers_survived_mutation")
    _require("tokenizer.json" in pinned.buffers and "preprocessor_config.json" in pinned.buffers,
             "namespace_keys_intact")

    # Step 8: Publish admitted engine under owner lock
    owner._publish_admitted_engine(attempt)

    return OwnedASREngine(owner, pipeline, model, vad, namespace_lease, attempt.generation)


def construct_owned_asr_engine(
    bootstrap,
    policy: _EngineConstructionPolicy,
    *,
    whisper_model_cls=None,
    tokenizer_cls=None,
    options_cls=None,
    pipeline_cls=None,
) -> OwnedASREngine:
    """Entry point delegating construction to WorkerBootstrap._build_admitted_engine inside one owner operation."""
    _require(bootstrap is not None, "worker_bootstrap_required")
    _require(getattr(bootstrap, '_ready', False) and getattr(bootstrap, '_started', False)
             and not getattr(bootstrap, '_closed', False), "worker_bootstrap_not_ready_or_closed")
    return bootstrap._build_admitted_engine(
        policy=policy,
        whisper_model_cls=whisper_model_cls,
        tokenizer_cls=tokenizer_cls,
        options_cls=options_cls,
        pipeline_cls=pipeline_cls,
    )
