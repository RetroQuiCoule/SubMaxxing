"""
Transcriber module for Submaxxing.
Runs local Whisper models (e.g. large-v3-turbo) using faster-whisper with CUDA acceleration.
Generates word-level timestamps directly from video or audio files.
"""

import os
import sys

# 1. Suppress HuggingFace symlinks warning on Windows
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

# 2. Add NVIDIA CUDA/cuDNN DLL directories to PATH on Windows if installed
if sys.platform == "win32":
    import site
    for site_pkg in site.getsitepackages():
        for sub in [("nvidia", "cublas", "bin"), ("nvidia", "cudnn", "bin")]:
            bin_dir = os.path.join(site_pkg, *sub)
            if os.path.isdir(bin_dir):
                try:
                    os.add_dll_directory(bin_dir)
                except Exception:
                    pass
                os.environ["PATH"] = bin_dir + ";" + os.environ.get("PATH", "")

# 3. Patch PyAV metadata_errors bug in newer av versions (av >= 14/19)
try:
    import av
    _orig_av_open = av.open

    def _safe_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)

    av.open = _safe_av_open
except Exception:
    pass

from typing import List, Optional, Tuple
from faster_whisper import WhisperModel
from styles import WordTiming, SubChunk
from chunker import group_words_into_chunks, merge_french_elisions


def format_srt_time(seconds: float) -> str:
    """Formats seconds to SRT format: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        secs += 1
        millis -= 1000
    return f"{hrs:02d}:{mins:02d}:{secs:02d},{millis:03d}"


def get_whisper_model(model_name: str = "large-v3-turbo", device: str = "auto", compute_type: str = "auto") -> WhisperModel:
    """Loads WhisperModel with automatic CUDA detection and seamless CPU fallback."""
    import ctranslate2

    if device == "auto":
        has_cuda = ctranslate2.get_cuda_device_count() > 0
        device = "cuda" if has_cuda else "cpu"

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    print(f"[*] Chargement du modèle Whisper '{model_name}' (téléchargement automatique lors de la 1ère utilisation)...")
    if device == "cuda":
        try:
            print(f"[*] Exécution sur GPU RTX (CUDA {compute_type})...")
            return WhisperModel(model_name, device="cuda", compute_type=compute_type)
        except Exception as e:
            print(f"[!] Avertissement GPU ({e}), bascule automatique sur CPU (int8)...")
            return WhisperModel(model_name, device="cpu", compute_type="int8")
    else:
        print(f"[*] Exécution sur CPU (mode int8)...")
        return WhisperModel(model_name, device="cpu", compute_type="int8")


def transcribe_video(
    media_path: str,
    model_name: str = "large-v3-turbo",
    language: Optional[str] = "fr",
    max_words: int = 2,
    device: str = "auto",
    compute_type: str = "auto",
) -> Tuple[List[SubChunk], str]:
    """
    Transcribes media_path directly, extracts word-level timestamps,
    and returns (chunks, full_srt_string).
    """
    if not os.path.exists(media_path):
        raise FileNotFoundError(f"Fichier média introuvable: {media_path}")

    model = get_whisper_model(model_name=model_name, device=device, compute_type=compute_type)

    print(f"[*] Transcription en cours: '{media_path}' (Langue: {language or 'auto'}, Timestamps par mot activés)...")
    segments, info = model.transcribe(
        media_path,
        language=language,
        word_timestamps=True,
        vad_filter=True,
        vad_parameters=dict(min_silence_duration_ms=400),
    )

    all_word_timings: List[WordTiming] = []
    srt_lines: List[str] = []

    for segment in segments:
        if segment.words:
            for w in segment.words:
                cleaned_word = w.word.strip()
                if cleaned_word:
                    all_word_timings.append(WordTiming(
                        word=cleaned_word,
                        start=w.start,
                        end=w.end
                    ))
        else:
            words = segment.text.strip().split()
            if words:
                seg_dur = max(0.1, segment.end - segment.start)
                per_word = seg_dur / len(words)
                for i, w in enumerate(words):
                    all_word_timings.append(WordTiming(
                        word=w,
                        start=segment.start + i * per_word,
                        end=segment.start + (i + 1) * per_word
                    ))

    # Merge French clitics (c', d', l', j', qu') so they are never isolated
    all_word_timings = merge_french_elisions(all_word_timings)
    chunks = group_words_into_chunks(all_word_timings, max_words=max_words)

    for i, c in enumerate(chunks, start=1):
        text = " ".join(w.word for w in c.words)
        srt_lines.append(f"{i}")
        srt_lines.append(f"{format_srt_time(c.start)} --> {format_srt_time(c.end)}")
        srt_lines.append(text)
        srt_lines.append("")

    srt_content = "\n".join(srt_lines)
    print(f"[+] Transcription terminée: {len(all_word_timings)} mots, {len(chunks)} paquets.")
    return chunks, srt_content
