import os
from whisperx._uoink_owned import require_owned_runtime, validate_waveform

require_owned_runtime()

from typing import Optional, Union

import numpy as np
import torch
import torch.nn.functional as F

from whisperx.utils import exact_div

# hard-coded audio hyperparameters
SAMPLE_RATE = 16000
N_FFT = 400
HOP_LENGTH = 160
CHUNK_LENGTH = 30
N_SAMPLES = CHUNK_LENGTH * SAMPLE_RATE  # 480000 samples in a 30-second chunk
N_FRAMES = exact_div(N_SAMPLES, HOP_LENGTH)  # 3000 frames in a mel spectrogram input

N_SAMPLES_PER_TOKEN = HOP_LENGTH * 2  # the initial convolutions has stride 2
FRAMES_PER_SECOND = exact_div(SAMPLE_RATE, HOP_LENGTH)  # 10ms per audio frame
TOKENS_PER_SECOND = exact_div(SAMPLE_RATE, N_SAMPLES_PER_TOKEN)  # 20ms per audio token


def load_audio(file: str, sr: int = SAMPLE_RATE) -> np.ndarray:
    raise NotImplementedError("Use the owned validated waveform decoder")


def pad_or_trim(array, length: int = N_SAMPLES, *, axis: int = -1):
    """
    Pad or trim the audio array to N_SAMPLES, as expected by the encoder.
    """
    if torch.is_tensor(array):
        if array.shape[axis] > length:
            array = array.index_select(
                dim=axis, index=torch.arange(length, device=array.device)
            )

        if array.shape[axis] < length:
            pad_widths = [(0, 0)] * array.ndim
            pad_widths[axis] = (0, length - array.shape[axis])
            array = F.pad(array, [pad for sizes in pad_widths[::-1] for pad in sizes])
    else:
        if array.shape[axis] > length:
            array = array.take(indices=range(length), axis=axis)

        if array.shape[axis] < length:
            pad_widths = [(0, 0)] * array.ndim
            pad_widths[axis] = (0, length - array.shape[axis])
            array = np.pad(array, pad_widths)

    return array


def mel_filters(device, n_mels: int) -> torch.Tensor:
    """Use the runtime-owned, separately admitted filter bank; never load an NPZ."""
    if type(n_mels) is not int or n_mels not in (80, 128):
        raise ValueError("Only 80- and 128-band filter banks are supported")
    matrix = require_owned_runtime().get_mel_filters(n_mels)
    if (type(matrix) is not np.ndarray or matrix.dtype != np.dtype("float32")
            or matrix.shape != (n_mels, N_FFT // 2 + 1)
            or not matrix.flags.c_contiguous or not np.isfinite(matrix).all()):
        raise ValueError("An admitted finite float32 filter bank is required")
    # The runtime owns caching and tensor lifetime; no process-global cache
    # may retain a prior session's asset or native object.
    return torch.from_numpy(matrix).to(device)


def log_mel_spectrogram(
    audio: np.ndarray,
    n_mels: int,
    padding: int = 0,
    device: Optional[Union[str, torch.device]] = None,
):
    """
    Compute the log-Mel spectrogram of

    Parameters
    ----------
    audio: np.ndarray, shape = (samples,)
        A validated mono float32 waveform at 16 kHz.

    n_mels: int
        The number of Mel-frequency filters, only 80 is supported

    padding: int
        Number of zero samples to pad to the right

    device: Optional[Union[str, torch.device]]
        If given, the audio tensor is moved to this device before STFT

    Returns
    -------
    torch.Tensor, shape = (80, n_frames)
        A Tensor that contains the Mel spectrogram
    """
    audio = torch.from_numpy(validate_waveform(audio))

    if device is not None:
        audio = audio.to(device)
    if padding > 0:
        audio = F.pad(audio, (0, padding))
    window = torch.hann_window(N_FFT).to(audio.device)
    stft = torch.stft(audio, N_FFT, HOP_LENGTH, window=window, return_complex=True)
    magnitudes = stft[..., :-1].abs() ** 2

    filters = mel_filters(audio.device, n_mels)
    mel_spec = filters @ magnitudes

    log_spec = torch.clamp(mel_spec, min=1e-10).log10()
    log_spec = torch.maximum(log_spec, log_spec.max() - 8.0)
    log_spec = (log_spec + 4.0) / 4.0
    return log_spec
