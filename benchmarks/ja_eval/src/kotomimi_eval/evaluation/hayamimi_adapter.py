from __future__ import annotations

import glob
from pathlib import Path
import sys
import time

import numpy as np
import soundfile as sf

from ..errors import ModelEvaluationUnavailable
from ..hashing import sha256_file
from ..paths import REPO_ROOT


MODEL_DIR = REPO_ROOT / "models" / "sherpa-onnx-zipformer-ja-en-reazonspeech-2025-01-17"


class HayamimiAdapter:
    system_id = "hayamimi-ja"

    def __init__(self, *, threads: int, punctuate: bool):
        if not self.available():
            raise ModelEvaluationUnavailable(
                "Japanese ASR model is missing; run scripts/download_models.py --minimal")
        scripts = str(REPO_ROOT / "scripts")
        if scripts not in sys.path:
            sys.path.insert(0, scripts)
        from asr_engine import RoutedASR

        self.threads = threads
        self.punctuate = punctuate
        self.asr = RoutedASR(
            threads=threads, warmup=True, preload=False,
            forced_lang="ja", punctuate=punctuate)

    @staticmethod
    def available() -> bool:
        return bool(
            list(MODEL_DIR.glob("encoder-*.int8.onnx"))
            and list(MODEL_DIR.glob("decoder-*.int8.onnx"))
            and list(MODEL_DIR.glob("joiner-*.int8.onnx"))
            and (MODEL_DIR / "tokens.txt").is_file()
        )

    @staticmethod
    def model_hashes() -> dict[str, str]:
        patterns = ("encoder-*.int8.onnx", "decoder-*.int8.onnx", "joiner-*.int8.onnx")
        files = [Path(sorted(glob.glob(str(MODEL_DIR / pattern)))[0]) for pattern in patterns]
        files.append(MODEL_DIR / "tokens.txt")
        return {path.name: f"sha256:{sha256_file(path)}" for path in files}

    def transcribe_file(self, path: str | Path) -> dict:
        samples, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
        if samples.ndim != 1:
            raise RuntimeError("prepared evaluation audio must be mono")
        started = time.perf_counter()
        result = self.asr.transcribe(
            np.asarray(samples, dtype=np.float32), sample_rate,
            known_lang="ja", speech_s=len(samples) / sample_rate, live=False)
        latency_ms = (time.perf_counter() - started) * 1000
        return {
            "text": result["text"],
            "lang": result["lang"],
            "tier": result.get("tier", ""),
            "latency_ms": latency_ms,
        }
