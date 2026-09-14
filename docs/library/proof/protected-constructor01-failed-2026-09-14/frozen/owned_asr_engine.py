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


class OwnedASREngine:
    """Worker-owned ASR engine identity wrapping the private constructed pipeline.

    Retains references to the underlying pipeline, model, VAD product, admitted namespace,
    and runtime owner generation. Does not expose bare models to callers.
    """
    __slots__ = ('_owner', '_pipeline', '_model', '_vad', '_namespace_record', '_generation', '_active')

    def __init__(self, owner, pipeline, model, vad, namespace_record, generation):
        self._owner = owner
        self._pipeline = pipeline
        self._model = model
        self._vad = vad
        self._namespace_record = namespace_record
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
    def namespace_record(self):
        self.assert_bound()
        return self._namespace_record

    @property
    def generation(self):
        return self._generation

    @property
    def active(self):
        return self._active and getattr(self._owner, '_active', False)

    def assert_bound(self):
        _require(self._active is True, "engine_ownership_revoked")
        _require(self._generation is self._owner._generation, "engine_generation_mismatch")
        self._owner.assert_engine_binding(self)

    def retire(self, permit):
        _require(self._active is True, "engine_already_retired")
        self._owner.retire_engine_product(permit, self)
        self._active = False


def construct_owned_asr_engine(
    bootstrap,
    namespace_record,
    vad_model,
    *,
    device: str = "cpu",
    compute_type: str = "int8",
    cpu_threads: int = 4,
    asr_options: Optional[dict] = None,
    vad_options: Optional[dict] = None,
    language: Optional[str] = None,
    task: str = "transcribe",
    pipeline_constructor = None,
) -> OwnedASREngine:
    """Connect engine ownership to the existing worker owner and construct the private owned ASR engine.

    Enforces:
    - Admitted namespace binding and active read set
    - Actual owned factory's VAD identity
    - Fixed CPU/int8 policy (device='cpu', compute_type='int8')
    - Required tokenizer bytes; every filesystem/Hub fallback is refused
    - Four-file schema absent preprocessor explicit captured feature defaults policy;
      B3 companion delta identified and path closed for separate qualification
    - Five-file fresh files map forwarding into constructor, surviving dictionary pops
    - Connection to worker owner before constructors or fallible work can lose references
    - Recheck of namespace, model/VAD, and operation identities before returning private engine
    - First error preservation and uncertain ownership retention for process-retirement path
    """
    _require(bootstrap is not None, "worker_bootstrap_required")
    _require(getattr(bootstrap, '_ready', False) and getattr(bootstrap, '_started', False)
             and not getattr(bootstrap, '_closed', False), "worker_bootstrap_not_ready_or_closed")
    owner = bootstrap.registry
    _require(owner is not None and getattr(owner, '_active', False), "active_worker_owner_required")

    # Enforce fixed CPU/int8 policy before any constructor entry
    _require(device == "cpu", "device_policy_cpu_required")
    _require(compute_type == "int8", "compute_type_policy_int8_required")
    _require(isinstance(cpu_threads, int) and cpu_threads > 0, "cpu_threads_positive_int_required")

    # Enforce VAD identity before constructor
    _require(vad_model is not None, "vad_model_required")
    owner.assert_vad_binding(vad_model)

    # Enforce namespace record identity before constructor
    _require(namespace_record is not None, "namespace_record_required")
    owner.assert_admitted_namespace_binding(namespace_record)

    pinned = getattr(namespace_record, 'namespace', getattr(namespace_record, '_namespace', None))
    _require(pinned is not None and getattr(pinned, '_ready', False), "materialized_pinned_namespace_required")
    buffers = pinned.buffers
    _require(type(buffers) is MappingProxyType and len(buffers) in (4, 5), "immutable_namespace_buffers_required")

    # Require tokenizer bytes and refuse every filesystem/Hub fallback
    _require("tokenizer.json" in buffers, "tokenizer_bytes_required")
    tokenizer_bytes = buffers["tokenizer.json"]
    _require(isinstance(tokenizer_bytes, bytes) and len(tokenizer_bytes) > 0, "nonempty_tokenizer_bytes_required")

    # Check four-file schema vs five-file schema
    names = frozenset(buffers.keys())
    _require(names in (FOUR, FIVE), "schema_must_be_four_or_five_files")

    if "preprocessor_config.json" not in buffers:
        # Four-file schema's absent preprocessor: handle with explicit captured feature defaults.
        # Do not fabricate a preprocessor asset or weaken existing five-file refusal.
        # B3 as written probes os.path.isfile(config_path) when preprocessor_bytes is None.
        # Without companion delta, path probe is unmitigated; leave that path closed for separate qualification.
        _ = FEATURE_EXTRACTOR_DEFAULTS
        raise EngineRefusal("four_file_preprocessor_path_probe_requires_b3_companion_delta: " + COMPANION_DELTA_B3_NO_PATH)

    # Five-file schema: enter engine operation scope on worker owner
    first_error = None
    with owner.operation(bootstrap._permit, "engine") as token:
        # Connect engine ownership before constructors or other fallible work can lose references
        owner.connect_engine_before_construction(bootstrap._permit, namespace_record, vad_model)
        try:
            # Forward a fresh files map into constructor; immutable source namespace survives dictionary pops
            fresh_files = pinned.fresh_files_map()
            _require(fresh_files is not buffers, "files_map_must_be_fresh_copy")

            if pipeline_constructor is None:
                from whisperx.asr import load_owned_model_from_namespace
                pipeline_constructor = load_owned_model_from_namespace

            pipeline = pipeline_constructor(
                namespace_record,
                vad_model,
                files=fresh_files,
                device="cpu",
                device_index=0,
                compute_type="int8",
                threads=cpu_threads,
                asr_options=asr_options,
                vad_options=vad_options,
                language=language,
                task=task,
                runtime=owner,
            )
            _require(pipeline is not None and hasattr(pipeline, "model"), "valid_constructed_pipeline_required")

            # Verify immutable source namespace survived constructor's dictionary pops
            _require(len(pinned.buffers) == 5, "namespace_buffers_survived_constructor_pops")
            _require("tokenizer.json" in pinned.buffers and "preprocessor_config.json" in pinned.buffers,
                     "namespace_keys_intact")

            engine = OwnedASREngine(
                owner=owner,
                pipeline=pipeline,
                model=pipeline.model,
                vad=vad_model,
                namespace_record=namespace_record,
                generation=owner._generation,
            )

            # Register engine ownership before returning
            owner.register_engine_product(
                bootstrap._permit, engine, pipeline, pipeline.model, vad_model, namespace_record)

            # Recheck namespace, model/VAD and operation identities before returning
            owner.assert_admitted_namespace_binding(namespace_record)
            owner.assert_vad_binding(vad_model)
            owner.assert_engine_binding(engine)

            return engine

        except BaseException as original:
            first_error = original
            try:
                owner.quarantine_engine(bootstrap._permit, namespace_record, vad_model, original)
            except BaseException as cleanup:
                BaseException.add_note(original, "Engine quarantine remains unconfirmed: " + type(cleanup).__name__)
            raise
