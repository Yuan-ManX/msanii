import math
import numbers

import numpy as np
import torch
from einops import rearrange
from torch import Tensor
from torch.nn import functional as F
from torchaudio import functional as AF


def classname_from_class(classpath) -> str:
    return str(classpath).rsplit(".", maxsplit=1)[1].strip("'>\"")


def compute_divisible_length(
    curr_length: int, hop_length: int, num_downsamples: int
) -> int:
    # Current time frame size
    num_time_frames = int((curr_length / hop_length) + 1)
    # Divisible time frames
    divisible_time_frames = math.ceil(num_time_frames / 2**num_downsamples) * (
        2**num_downsamples
    )
    divisible_length = (divisible_time_frames - 1) * hop_length

    return divisible_length


def pad_to_divisible_length(
    x: Tensor, hop_length: int, num_downsamples: int, pad_end: bool = True
) -> Tensor:
    divisible_length = compute_divisible_length(
        x.shape[-1], hop_length, num_downsamples
    )
    # Pad to appropriate length
    if pad_end:
        x = F.pad(x, (0, divisible_length - x.shape[-1]))
    else:
        x = F.pad(x, (divisible_length - x.shape[-1], 0))

    return x


def gradio_audio_preprocessing(
    audio: np.ndarray,
    src_sample_rate: int,
    target_sample_rate: int,
    target_length: int,
    hop_length: int,
    num_downsamples: int,
    dtype: torch.dtype,
    device: torch.device,
    pad_end: bool = True,
) -> Tensor:
    # Ensure audio is a float tensor between [-1, 1]
    if issubclass(audio.dtype.type, numbers.Integral):
        audio = audio / np.iinfo(audio.dtype).max

    # Load audio into tensor and resample
    audio = torch.from_numpy(audio)
    if audio.ndim == 1:
        audio = rearrange(audio, "l -> () () l")  # to batched and mono-channels
    else:
        audio = rearrange(audio, "l c -> () c l")  # to batched channel first
    audio = AF.resample(audio, src_sample_rate, target_sample_rate)

    # Rescale target length by the sample rate
    target_length = int((target_length * target_sample_rate) / src_sample_rate)

    # Pad audio to the target length
    if pad_end:
        audio = F.pad(audio, (0, target_length - audio.shape[-1]))
    else:
        audio = F.pad(audio, (target_length - audio.shape[-1], 0))

    # Pad audio to a length divisible by the number of downsampling layers
    audio = pad_to_divisible_length(audio, hop_length, num_downsamples, pad_end)

    # Switch target dtype and device
    audio = audio.to(dtype).to(device)

    return audio


def gradio_audio_postprocessing(
    audio: Tensor, target_length: int, pad_end: bool = True
) -> np.ndarray:
    # Ensure audio is the correct length
    if pad_end:
        audio = F.pad(audio, (0, target_length - audio.shape[-1]))
    else:
        audio = F.pad(audio, (target_length - audio.shape[-1], 0))

    # Remove batch dimension & switch to channels last
    audio = rearrange(audio, "b c l -> (l b) c")

    return audio.detach().cpu().numpy()


def generate_gradio_audio_mask(
    audio: np.ndarray, sample_rate: int, spec: str
) -> np.ndarray:
    # Convert mask string to a list of tuples of time intevals
    mask_intervals = []
    for mask in spec.split(","):
        start, end = map(int, mask.split("-"))
        mask_intervals.append((start, end))

    # Create a numpy array of zeros with the same shape as input
    mask = np.ones_like(audio)

    # Set the values at the specified time intervals to 1
    for start, end in mask_intervals:
        start_sample = int(start * sample_rate)
        end_sample = int(end * sample_rate)
        mask[start_sample:end_sample, ...] = 0

    return mask


def max_abs_scaling(x: Tensor, max_abs_value: float = 0.05) -> Tensor:
    x = x / x.abs().max()
    x = x * max_abs_value

    return x
