import os
from whisperx._uoink_owned import require_owned_runtime, require_owned_model, validate_waveform

require_owned_runtime()

from typing import List, Optional, Union
from dataclasses import replace

import ctranslate2
import faster_whisper
import numpy as np
import torch
from faster_whisper.tokenizer import Tokenizer
from faster_whisper.transcribe import TranscriptionOptions, get_ctranslate2_storage
from transformers import Pipeline
from transformers.pipelines.pt_utils import PipelineIterator

from whisperx.audio import N_SAMPLES, SAMPLE_RATE, log_mel_spectrogram
from whisperx.schema import SingleSegment, TranscriptionResult, ProgressCallback
from whisperx.vads.pyannote import Pyannote, VoiceActivitySegmentation
from whisperx.log_utils import get_logger

logger = get_logger(__name__)

COMPANION_DELTA_B3_NO_PATH = (
    "In B3 WhisperModel._get_feature_kwargs (B2.py:741), when preprocessor_bytes is None "
    "and files is provided, B3 probes os.path.isfile(config_path). Companion delta must guard "
    "with 'not files and os.path.isfile' or return captured feature extractor defaults without probing filesystem."
)


def find_numeral_symbol_tokens(tokenizer):
    numeral_symbol_tokens = []
    for i in range(tokenizer.eot):
        token = tokenizer.decode([i]).removeprefix(" ")
        has_numeral_symbol = any(c in "0123456789%$£" for c in token)
        if has_numeral_symbol:
            numeral_symbol_tokens.append(i)
    return numeral_symbol_tokens

class WhisperModel(faster_whisper.WhisperModel):
    '''
    FasterWhisperModel provides batched inference for faster-whisper.
    Currently only works in non-timestamp mode and fixed prompt for all samples in batch.
    '''

    def generate_segment_batched(
        self,
        features: np.ndarray,
        tokenizer: Tokenizer,
        options: TranscriptionOptions,
        encoder_output=None,
    ):
        batch_size = features.shape[0]
        all_tokens = []
        prompt_reset_since = 0
        if options.initial_prompt is not None:
            initial_prompt = " " + options.initial_prompt.strip()
            initial_prompt_tokens = tokenizer.encode(initial_prompt)
            all_tokens.extend(initial_prompt_tokens)
        previous_tokens = all_tokens[prompt_reset_since:]
        prompt = self.get_prompt(
            tokenizer,
            previous_tokens,
            without_timestamps=options.without_timestamps,
            prefix=options.prefix,
            hotwords=options.hotwords
        )

        encoder_output = self.encode(features)
        
        result = self.model.generate(
                encoder_output,
                [prompt] * batch_size,
                beam_size=options.beam_size,
                patience=options.patience,
                length_penalty=options.length_penalty,
                max_length=self.max_length,
                suppress_blank=options.suppress_blank,
                suppress_tokens=options.suppress_tokens,
                no_repeat_ngram_size=options.no_repeat_ngram_size,
                repetition_penalty=options.repetition_penalty,
                return_scores=True,
            )

        tokens_batch = [x.sequences_ids[0] for x in result]

        avg_logprobs = []
        for res in result:
            seq_len = len(res.sequences_ids[0])
            cum_logprob = res.scores[0] * (seq_len ** options.length_penalty)
            avg_logprobs.append(cum_logprob / (seq_len + 1))

        def decode_batch(tokens: List[List[int]]) -> List[str]:
            res = []
            for tk in tokens:
                res.append([token for token in tk if token < tokenizer.eot])
            # text_tokens = [token for token in tokens if token < self.eot]
            return tokenizer.tokenizer.decode_batch(res)

        text = decode_batch(tokens_batch)

        return {'text': text, 'avg_logprob': avg_logprobs}

    def encode(self, features: np.ndarray) -> ctranslate2.StorageView:
        # When the model is running on multiple GPUs, the encoder output should be moved
        # to the CPU since we don't know which GPU will handle the next job.
        to_cpu = self.model.device == "cuda" and len(self.model.device_index) > 1
        # unsqueeze if batch size = 1
        if len(features.shape) == 2:
            features = np.expand_dims(features, 0)
        features = get_ctranslate2_storage(features)

        return self.model.encode(features, to_cpu=to_cpu)

class FasterWhisperPipeline(Pipeline):
    """
    Huggingface Pipeline wrapper for FasterWhisperModel.
    """
    # TODO:
    # - add support for timestamp mode
    # - add support for custom inference kwargs

    def __init__(
        self,
        model: WhisperModel,
        vad,
        vad_params: dict,
        options: TranscriptionOptions,
        tokenizer: Optional[Tokenizer] = None,
        device: Union[int, str, "torch.device"] = -1,
        framework="pt",
        language: Optional[str] = None,
        suppress_numerals: bool = False,
        **kwargs,
    ):
        self.model = model
        self.tokenizer = tokenizer
        self.options = options
        self.preset_language = language
        self.suppress_numerals = suppress_numerals
        self._batch_size = kwargs.pop("batch_size", None)
        self._num_workers = 1
        self._preprocess_params, self._forward_params, self._postprocess_params = self._sanitize_parameters(**kwargs)
        self.call_count = 0
        self.framework = framework
        if self.framework == "pt":
            if isinstance(device, torch.device):
                self.device = device
            elif isinstance(device, str):
                self.device = torch.device(device)
            elif device < 0:
                self.device = torch.device("cpu")
            else:
                self.device = torch.device(f"cuda:{device}")
        else:
            self.device = device

        super(Pipeline, self).__init__()
        self.vad_model = vad
        self._vad_params = vad_params

    def _sanitize_parameters(self, **kwargs):
        preprocess_kwargs = {}
        if "tokenizer" in kwargs:
            preprocess_kwargs["maybe_arg"] = kwargs["maybe_arg"]
        return preprocess_kwargs, {}, {}

    def preprocess(self, audio):
        audio = audio['inputs']
        model_n_mels = self.model.feat_kwargs.get("feature_size")
        features = log_mel_spectrogram(
            audio,
            n_mels=model_n_mels if model_n_mels is not None else 80,
            padding=N_SAMPLES - audio.shape[0],
        )
        return {'inputs': features}

    def _forward(self, model_inputs):
        outputs = self.model.generate_segment_batched(model_inputs['inputs'], self.tokenizer, self.options)
        return outputs

    def postprocess(self, model_outputs):
        return model_outputs

    def get_iterator(
        self,
        inputs,
        num_workers: int,
        batch_size: int,
        preprocess_params: dict,
        forward_params: dict,
        postprocess_params: dict,
    ):
        dataset = PipelineIterator(inputs, self.preprocess, preprocess_params)
        if "TOKENIZERS_PARALLELISM" not in os.environ:
            os.environ["TOKENIZERS_PARALLELISM"] = "false"
        # TODO hack by collating feature_extractor and image_processor

        def stack(items):
            return {'inputs': torch.stack([x['inputs'] for x in items])}
        dataloader = torch.utils.data.DataLoader(dataset, num_workers=num_workers, batch_size=batch_size, collate_fn=stack)
        model_iterator = PipelineIterator(dataloader, self.forward, forward_params, loader_batch_size=batch_size)
        final_iterator = PipelineIterator(model_iterator, self.postprocess, postprocess_params)
        return final_iterator

    def transcribe(
        self,
        audio: np.ndarray,
        batch_size: Optional[int] = None,
        num_workers=0,
        language: Optional[str] = None,
        task: Optional[str] = None,
        chunk_size=30,
        print_progress=False,
        combined_progress=False,
        verbose=False,
        progress_callback: ProgressCallback = None,
    ) -> TranscriptionResult:
        audio = validate_waveform(audio, owned_input=True)

        def data(audio, segments):
            for seg in segments:
                f1 = int(seg['start'] * SAMPLE_RATE)
                f2 = int(seg['end'] * SAMPLE_RATE)
                # print(f2-f1)
                yield {'inputs': audio[f1:f2]}

        # The owned factory injects this fixed segmentation pipeline. No VAD
        # selection or construction is performed during transcription.
        require_owned_runtime().assert_model_binding(self.model_path, self.vad_model)
        waveform = Pyannote.preprocess_audio(audio)
        merge_chunks = Pyannote.merge_chunks

        vad_segments = self.vad_model({"waveform": waveform, "sample_rate": SAMPLE_RATE})
        vad_segments = merge_chunks(
            vad_segments,
            chunk_size,
            onset=self._vad_params["vad_onset"],
            offset=self._vad_params["vad_offset"],
        )
        if self.tokenizer is None:
            language = language or self.detect_language(audio)
            task = task or "transcribe"
            self.tokenizer = Tokenizer(
                self.model.hf_tokenizer,
                self.model.model.is_multilingual,
                task=task,
                language=language,
            )
        else:
            language = language or self.tokenizer.language_code
            task = task or self.tokenizer.task
            if task != self.tokenizer.task or language != self.tokenizer.language_code:
                self.tokenizer = Tokenizer(
                    self.model.hf_tokenizer,
                    self.model.model.is_multilingual,
                    task=task,
                    language=language,
                )

        if self.suppress_numerals:
            previous_suppress_tokens = self.options.suppress_tokens
            numeral_symbol_tokens = find_numeral_symbol_tokens(self.tokenizer)
            logger.info("Suppressing numeral and symbol tokens")
            new_suppressed_tokens = numeral_symbol_tokens + self.options.suppress_tokens
            new_suppressed_tokens = list(set(new_suppressed_tokens))
            self.options = replace(self.options, suppress_tokens=new_suppressed_tokens)

        segments: List[SingleSegment] = []
        batch_size = batch_size or self._batch_size
        total_segments = len(vad_segments)
        for idx, out in enumerate(self.__call__(data(audio, vad_segments), batch_size=batch_size, num_workers=num_workers)):
            if print_progress:
                base_progress = ((idx + 1) / total_segments) * 100
                percent_complete = base_progress / 2 if combined_progress else base_progress
                print(f"Progress: {percent_complete:.2f}%...")
            if progress_callback is not None:
                progress_callback(((idx + 1) / total_segments) * 100)
            text = out['text']
            avg_logprob = out['avg_logprob']
            if batch_size in [0, 1, None]:
                text = text[0]
                avg_logprob = avg_logprob[0]
            if verbose:
                print(f"Transcript: [{round(vad_segments[idx]['start'], 3)} --> {round(vad_segments[idx]['end'], 3)}] {text}")
            segments.append(
                {
                    "text": text,
                    "start": round(vad_segments[idx]['start'], 3),
                    "end": round(vad_segments[idx]['end'], 3),
                    "avg_logprob": avg_logprob,
                }
            )

        # revert the tokenizer if multilingual inference is enabled
        if self.preset_language is None:
            self.tokenizer = None

        # revert suppressed tokens if suppress_numerals is enabled
        if self.suppress_numerals:
            self.options = replace(self.options, suppress_tokens=previous_suppress_tokens)

        return {"segments": segments, "language": language}

    def detect_language(self, audio: np.ndarray) -> str:
        audio = validate_waveform(audio)
        if audio.shape[0] < N_SAMPLES:
            logger.warning("Audio is shorter than 30s, language detection may be inaccurate")
        model_n_mels = self.model.feat_kwargs.get("feature_size")
        segment = log_mel_spectrogram(audio[: N_SAMPLES],
                                      n_mels=model_n_mels if model_n_mels is not None else 80,
                                      padding=0 if audio.shape[0] >= N_SAMPLES else N_SAMPLES - audio.shape[0])
        encoder_output = self.model.encode(segment)
        results = self.model.model.detect_language(encoder_output)
        language_token, language_probability = results[0][0]
        language = language_token[2:-2]
        logger.info(f"Detected language: {language} ({language_probability:.2f}) in first 30s of audio")
        return language


def load_model(
    whisper_arch: str,
    device: str,
    device_index=0,
    compute_type="default",
    asr_options: Optional[dict] = None,
    language: Optional[str] = None,
    vad_model: Optional[VoiceActivitySegmentation] = None,
    vad_method: Optional[str] = None,
    vad_options: Optional[dict] = None,
    model: Optional[WhisperModel] = None,
    task="transcribe",
    download_root: Optional[str] = None,
    local_files_only=True,
    threads=4,
    use_auth_token: Optional[Union[str, bool]] = None,
) -> FasterWhisperPipeline:
    """Load a Whisper model for inference.
    Args:
        whisper_arch - The exact admitted absolute local model snapshot path.
        device - The device to load the model on.
        compute_type - The exact compute type qualified in the owned profile.
            Automatic selection is unavailable.
        vad_model - The owned fixed VoiceActivitySegmentation instance.
        vad_method - Must be None; automatic VAD selection is unavailable.
        options - A dictionary of options to use for the model.
        language - The language of the model. (use English for now)
        model - Must be None; unbound constructor bypass is unavailable.
        download_root - Must be None; acquisition belongs to the consent service.
        local_files_only - Must be exactly True; no download or cache fallback.
        threads - The number of cpu threads to use per worker, e.g. will be multiplied by num workers.
    Returns:
        A Whisper pipeline.
    """

    require_owned_model(whisper_arch, vad_model)
    if type(vad_model) is not VoiceActivitySegmentation:
        raise ValueError("The owned fixed segmentation pipeline is required")
    if (local_files_only is not True or download_root is not None
            or use_auth_token is not None or model is not None or vad_method is not None):
        raise ValueError("Automatic loading, credentials and constructor bypass are unavailable")

    require_owned_runtime().assert_load_parameters(
        model_path=whisper_arch, vad_model=vad_model,
        device=device, device_index=device_index, compute_type=compute_type,
        threads=threads, language=language, task=task,
        asr_options=asr_options, vad_options=vad_options,
        local_files_only=local_files_only, download_root=download_root,
        use_auth_token=use_auth_token, model=model, vad_method=vad_method,
    )

    model = WhisperModel(whisper_arch,
                         device=device,
                         device_index=device_index,
                         compute_type=compute_type,
                         download_root=download_root,
                         local_files_only=local_files_only,
                         cpu_threads=threads,
                         use_auth_token=use_auth_token)
    if language is not None:
        tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task=task, language=language)
    else:
        logger.info("No language specified, language will be detected for each audio file (increases inference time)")
        tokenizer = None

    default_asr_options =  {
        "beam_size": 5,
        "best_of": 5,
        "patience": 1,
        "length_penalty": 1,
        "repetition_penalty": 1,
        "no_repeat_ngram_size": 0,
        "temperatures": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        "condition_on_previous_text": False,
        "prompt_reset_on_temperature": 0.5,
        "initial_prompt": None,
        "prefix": None,
        "suppress_blank": True,
        "suppress_tokens": [-1],
        "without_timestamps": True,
        "max_initial_timestamp": 0.0,
        "word_timestamps": False,
        "prepend_punctuations": "\"'“¿([{-",
        "append_punctuations": "\"'.。,，!！?？:：”)]}、",
        "multilingual": model.model.is_multilingual,
        "suppress_numerals": False,
        "max_new_tokens": None,
        "clip_timestamps": None,
        "hallucination_silence_threshold": None,
        "hotwords": None,
    }

    if asr_options is not None:
        default_asr_options.update(asr_options)

    suppress_numerals = default_asr_options["suppress_numerals"]
    del default_asr_options["suppress_numerals"]

    default_asr_options = TranscriptionOptions(**default_asr_options)

    default_vad_options = {
        "chunk_size": 30, # needed by silero since binarization happens before merge_chunks
        "vad_onset": 0.500,
        "vad_offset": 0.363
    }

    if vad_options is not None:
        default_vad_options.update(vad_options)

    pipeline = FasterWhisperPipeline(
        model=model,
        vad=vad_model,
        options=default_asr_options,
        tokenizer=tokenizer,
        language=language,
        suppress_numerals=suppress_numerals,
        vad_params=default_vad_options,
    )
    pipeline.model_path = whisper_arch
    return pipeline


def load_owned_model_from_namespace(
    namespace_record,
    vad_model: VoiceActivitySegmentation,
    *,
    files: dict,
    device: str = "cpu",
    device_index: int = 0,
    compute_type: str = "int8",
    threads: int = 4,
    asr_options: Optional[dict] = None,
    language: Optional[str] = None,
    vad_options: Optional[dict] = None,
    task: str = "transcribe",
    runtime=None,
) -> FasterWhisperPipeline:
    """Private owned WhisperX constructor entry consuming admitted namespace, fixed CPU/int8 policy, and owned VAD."""
    runtime = require_owned_runtime() if runtime is None else runtime
    runtime.assert_active()
    runtime.assert_vad_binding(vad_model)
    runtime.assert_admitted_namespace_binding(namespace_record)

    if device != "cpu" or compute_type != "int8" or device_index != 0:
        raise ValueError("Fixed CPU int8 policy required: device='cpu', compute_type='int8', device_index=0")
    if not isinstance(threads, int) or threads <= 0:
        raise ValueError("threads must be a positive integer")

    if type(files) is not dict or not files:
        raise ValueError("Nonempty fresh files dictionary is required")

    tokenizer_bytes = files.get("tokenizer.json")
    if tokenizer_bytes is None or type(tokenizer_bytes) is not bytes or len(tokenizer_bytes) == 0:
        raise ValueError("Tokenizer bytes are required; filesystem and Hub fallbacks are unavailable")

    if "preprocessor_config.json" not in files:
        # Four-file schema absent preprocessor: B3 as written probes os.path.isfile(config_path).
        # Without companion delta, path probe is unmitigated; leave path closed for separate qualification.
        raise ValueError("four_file_preprocessor_path_probe_requires_b3_companion_delta: " + COMPANION_DELTA_B3_NO_PATH)

    model_id = "uoink-memory-" + namespace_record.namespace.namespace_sha256

    model = WhisperModel(
        model_id,
        device="cpu",
        device_index=0,
        compute_type="int8",
        download_root=None,
        local_files_only=True,
        files=files,
        cpu_threads=threads,
        use_auth_token=None,
    )

    if language is not None:
        tokenizer = Tokenizer(model.hf_tokenizer, model.model.is_multilingual, task=task, language=language)
    else:
        tokenizer = None

    default_asr_options = {
        "beam_size": 5,
        "best_of": 5,
        "patience": 1,
        "length_penalty": 1,
        "repetition_penalty": 1,
        "no_repeat_ngram_size": 0,
        "temperatures": [0.0, 0.2, 0.4, 0.6, 0.8, 1.0],
        "compression_ratio_threshold": 2.4,
        "log_prob_threshold": -1.0,
        "no_speech_threshold": 0.6,
        "condition_on_previous_text": False,
        "prompt_reset_on_temperature": 0.5,
        "initial_prompt": None,
        "prefix": None,
        "suppress_blank": True,
        "suppress_tokens": [-1],
        "without_timestamps": True,
        "max_initial_timestamp": 0.0,
        "word_timestamps": False,
        "prepend_punctuations": "\"'“¿([{-",
        "append_punctuations": "\"'.。,，!！?？:：”)]}、",
        "multilingual": model.model.is_multilingual,
        "suppress_numerals": False,
        "max_new_tokens": None,
        "clip_timestamps": None,
        "hallucination_silence_threshold": None,
        "hotwords": None,
    }

    if asr_options is not None:
        default_asr_options.update(asr_options)

    suppress_numerals = default_asr_options["suppress_numerals"]
    del default_asr_options["suppress_numerals"]

    default_asr_options = TranscriptionOptions(**default_asr_options)

    default_vad_options = {
        "chunk_size": 30,
        "vad_onset": 0.500,
        "vad_offset": 0.363
    }

    if vad_options is not None:
        default_vad_options.update(vad_options)

    pipeline = FasterWhisperPipeline(
        model=model,
        vad=vad_model,
        options=default_asr_options,
        tokenizer=tokenizer,
        language=language,
        suppress_numerals=suppress_numerals,
        vad_params=default_vad_options,
    )
    pipeline.model_path = model_id
    return pipeline
