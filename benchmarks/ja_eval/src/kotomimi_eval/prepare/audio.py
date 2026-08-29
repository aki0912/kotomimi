from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import math
import os
from pathlib import Path
import subprocess

import numpy as np
import soundfile as sf

from ..errors import DatasetPreparationError


@dataclass(frozen=True)
class PreparedAudio:
    sample_rate: int
    channels: int
    duration_s: float
    pcm_sha256: str
    rms_dbfs: float | None
    peak: float
    clipped_fraction: float
    dc_offset: float
    flags: tuple[str, ...]

    def qc_dict(self) -> dict:
        data = asdict(self)
        data.pop("sample_rate")
        data.pop("channels")
        data.pop("duration_s")
        data.pop("pcm_sha256")
        data["flags"] = list(self.flags)
        data["hard_pass"] = True
        return data


def ffmpeg_version() -> str:
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"], capture_output=True, text=True,
            check=True, timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise DatasetPreparationError("ffmpeg is required for audio preparation") from exc
    return result.stdout.splitlines()[0].strip()


def convert_to_standard_flac(
    source: str | Path,
    destination: str | Path,
    *,
    timeout_s: float = 120.0,
) -> None:
    source_path = Path(source)
    destination_path = Path(destination)
    destination_path.parent.mkdir(parents=True, exist_ok=True)
    if destination_path.exists():
        validate_standard_flac(destination_path)
        return
    part = destination_path.with_name(destination_path.name + ".part")
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
        "-i", str(source_path), "-ac", "1", "-ar", "16000",
        "-sample_fmt", "s16", "-f", "flac", str(part),
    ]
    try:
        if part.exists():
            part.unlink()
        result = subprocess.run(
            command, capture_output=True, text=True, check=False, timeout=timeout_s)
        if result.returncode != 0:
            detail = result.stderr.strip().splitlines()[-1:] or ["unknown ffmpeg error"]
            raise DatasetPreparationError(f"ffmpeg conversion failed: {detail[0][:300]}")
        validate_standard_flac(part)
        os.replace(part, destination_path)
    except subprocess.TimeoutExpired as exc:
        raise DatasetPreparationError(f"ffmpeg conversion timed out for {source_path.name}") from exc
    finally:
        if part.exists():
            part.unlink()


def validate_standard_flac(path: str | Path) -> sf.SoundFile:
    try:
        info = sf.info(str(path))
    except (OSError, RuntimeError) as exc:
        raise DatasetPreparationError(f"cannot decode prepared audio {Path(path).name}") from exc
    if info.format != "FLAC" or info.samplerate != 16000 or info.channels != 1:
        raise DatasetPreparationError(
            f"prepared audio is not 16 kHz mono FLAC: {Path(path).name}")
    if info.subtype != "PCM_16":
        raise DatasetPreparationError(f"prepared FLAC is not PCM 16-bit: {Path(path).name}")
    return info


def inspect_prepared_audio(path: str | Path, thresholds: dict) -> PreparedAudio:
    info = validate_standard_flac(path)
    try:
        pcm, sample_rate = sf.read(str(path), dtype="int16", always_2d=False)
    except (OSError, RuntimeError) as exc:
        raise DatasetPreparationError(f"cannot read prepared audio {Path(path).name}") from exc
    if pcm.ndim != 1 or not len(pcm):
        raise DatasetPreparationError(f"prepared audio is empty or not mono: {Path(path).name}")
    floats = pcm.astype(np.float32) / 32768.0
    if not np.isfinite(floats).all():
        raise DatasetPreparationError(f"prepared audio contains NaN or Inf: {Path(path).name}")
    duration_s = len(pcm) / sample_rate
    if not thresholds["hard_min_duration_s"] <= duration_s <= thresholds["hard_max_duration_s"]:
        raise DatasetPreparationError(
            f"audio duration {duration_s:.3f}s is outside hard limits: {Path(path).name}")
    rms = float(np.sqrt(np.mean(np.square(floats, dtype=np.float64))))
    rms_dbfs = 20 * math.log10(rms) if rms > 0 else None
    peak = float(np.max(np.abs(floats)))
    clipped_fraction = float(np.mean(np.abs(floats) >= thresholds["clipping_amplitude"]))
    dc_offset = float(abs(np.mean(floats, dtype=np.float64)))
    flags = []
    if duration_s < thresholds["too_short_s"]:
        flags.append("too_short")
    if duration_s > thresholds["too_long_s"]:
        flags.append("too_long")
    if rms_dbfs is None or rms_dbfs < thresholds["very_quiet_dbfs"]:
        flags.append("very_quiet")
    if rms_dbfs is not None and rms_dbfs > thresholds["very_loud_dbfs"]:
        flags.append("very_loud")
    if clipped_fraction >= thresholds["clipping_fraction"]:
        flags.append("possible_clipping")
    if dc_offset > thresholds["dc_offset"]:
        flags.append("dc_offset")
    pcm_bytes = np.asarray(pcm, dtype="<i2").tobytes()
    return PreparedAudio(
        sample_rate=sample_rate,
        channels=info.channels,
        duration_s=duration_s,
        pcm_sha256=hashlib.sha256(pcm_bytes).hexdigest(),
        rms_dbfs=rms_dbfs,
        peak=peak,
        clipped_fraction=clipped_fraction,
        dc_offset=dc_offset,
        flags=tuple(flags),
    )
