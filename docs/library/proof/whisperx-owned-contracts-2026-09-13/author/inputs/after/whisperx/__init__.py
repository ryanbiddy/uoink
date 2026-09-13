import importlib

from whisperx._uoink_owned import require_owned_runtime


def _lazy_import(name):
    module = importlib.import_module(f"whisperx.{name}")
    return module


def load_align_model(*args, **kwargs):
    raise NotImplementedError("Alignment is unavailable in the owned non-speaker runtime")


def align(*args, **kwargs):
    raise NotImplementedError("Alignment is unavailable in the owned non-speaker runtime")


def load_model(*args, **kwargs):
    require_owned_runtime()
    asr = _lazy_import("asr")
    return asr.load_model(*args, **kwargs)


def load_audio(*args, **kwargs):
    raise NotImplementedError("Use the owned validated waveform decoder")


def assign_word_speakers(*args, **kwargs):
    raise NotImplementedError("Speaker attribution is unavailable in this runtime")


def setup_logging(*args, **kwargs):
    """
    Configure logging for WhisperX.

    Args:
        level: Logging level (debug, info, warning, error, critical). Default: warning
        log_file: Optional path to log file. If None, logs only to console.
    """
    logging_module = _lazy_import("log_utils")
    return logging_module.setup_logging(*args, **kwargs)


def get_logger(*args, **kwargs):
    """
    Get a logger instance for the given module.

    Args:
        name: Logger name (typically __name__ from calling module)

    Returns:
        Logger instance configured with WhisperX settings
    """
    logging_module = _lazy_import("log_utils")
    return logging_module.get_logger(*args, **kwargs)
