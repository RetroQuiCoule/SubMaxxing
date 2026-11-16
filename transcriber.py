"""
Transcriber module for Submaxxing.
Runs local Whisper models (e.g. large-v3-turbo) using faster-whisper with CUDA acceleration.
Includes smart caching, persistent word-level timestamps, and high-performance inference flags.
"""

import os
import sys
import json
import time
import hashlib
import tempfile
import threading
import subprocess
from typing import List, Optional, Tuple, Dict, Any, Callable

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

from faster_whisper import WhisperModel
from styles import WordTiming, SubChunk
from chunker import group_words_into_chunks, merge_french_elisions


# Global Cache & Concurrency Lock
_MODEL_CACHE: Dict[Tuple[str, str, str], WhisperModel] = {}
_MODEL_LOCK = threading.Lock()
_TRANSCRIPTION_MEMORY_CACHE: Dict[str, Tuple[List[WordTiming], str]] = {}


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
    """
    Loads WhisperModel with automatic CUDA detection and seamless CPU fallback.
    Caches the loaded model instance in memory so subsequent runs don't reload from disk.
    """
    import ctranslate2

    if device == "auto":
        has_cuda = ctranslate2.get_cuda_device_count() > 0
        device = "cuda" if has_cuda else "cpu"

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    cache_key = (model_name, device, compute_type)
    with _MODEL_LOCK:
        if cache_key in _MODEL_CACHE:
            return _MODEL_CACHE[cache_key]

        print(f"[*] Chargement du modèle Whisper '{model_name}' (device: {device}, compute: {compute_type})...")
        if device == "cuda":
            try:
                print(f"[*] Exécution sur GPU RTX (CUDA {compute_type})...")
                model = WhisperModel(model_name, device="cuda", compute_type=compute_type)
            except Exception as e:
                print(f"[!] Avertissement GPU ({e}), bascule automatique sur CPU (int8)...")
                model = WhisperModel(model_name, device="cpu", compute_type="int8")
        else:
            print(f"[*] Exécution sur CPU (mode int8)...")
            model = WhisperModel(model_name, device="cpu", compute_type="int8")

        _MODEL_CACHE[cache_key] = model
        return model


def _get_cache_key(media_path: str, language: Optional[str], model_name: str) -> str:
    """Generates a stable cache key based on path, file size, modification time, and language."""
    try:
        stat = os.stat(media_path)
        base = f"{os.path.abspath(media_path)}:{stat.st_size}:{stat.st_mtime}:{language or 'auto'}:{model_name}"
        return hashlib.sha256(base.encode("utf-8")).hexdigest()
    except Exception:
        return f"{media_path}:{language or 'auto'}:{model_name}"


def _get_disk_cache_path(media_path: str) -> str:
    """Returns the persistent JSON cache file path alongside the media file."""
    base_dir = os.path.dirname(os.path.abspath(media_path))
    file_name = os.path.basename(media_path)
    return os.path.join(base_dir, f".{file_name}.submaxxing_cache.json")


def load_cached_timings(media_path: str, language: Optional[str], model_name: str) -> Optional[Tuple[List[WordTiming], str]]:
    """Tries to retrieve pre-computed word timings from memory or disk cache."""
    key = _get_cache_key(media_path, language, model_name)
    if key in _TRANSCRIPTION_MEMORY_CACHE:
        return _TRANSCRIPTION_MEMORY_CACHE[key]

    cache_file = _get_disk_cache_path(media_path)
    if os.path.exists(cache_file):
        try:
            with open(cache_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("cache_key") == key:
                timings = [WordTiming(word=w["w"], start=w["s"], end=w["e"]) for w in data.get("words", [])]
                srt_content = data.get("srt", "")
                _TRANSCRIPTION_MEMORY_CACHE[key] = (timings, srt_content)
                return timings, srt_content
        except Exception:
            pass
    return None


def save_cached_timings(media_path: str, language: Optional[str], model_name: str, timings: List[WordTiming], srt_content: str):
    """Saves word timings to memory and disk cache for instantaneous reuse."""
    key = _get_cache_key(media_path, language, model_name)
    _TRANSCRIPTION_MEMORY_CACHE[key] = (timings, srt_content)

    cache_file = _get_disk_cache_path(media_path)
    try:
        data = {
            "cache_key": key,
            "created_at": time.time(),
            "words": [{"w": t.word, "s": round(t.start, 3), "e": round(t.end, 3)} for t in timings],
            "srt": srt_content
        }
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass


def transcribe_video(
    media_path: str,
    model_name: str = "large-v3-turbo",
    language: Optional[str] = "fr",
    max_words: int = 2,
    device: str = "auto",
    compute_type: str = "auto",
    use_cache: bool = True,
    duration_limit: Optional[float] = None,
    progress_callback: Optional[Callable[[float, float], None]] = None
) -> Tuple[List[SubChunk], str]:
    """
    Transcribes media_path directly, extracts word-level timestamps,
    and returns (chunks, full_srt_string).
    Uses high-speed greedy decoding (beam_size=1) and caching to eliminate redundant re-runs.
    """
    if not os.path.exists(media_path):
        raise FileNotFoundError(f"Fichier média introuvable: {media_path}")

    # Check cache first if not restricting to partial duration
    if use_cache and not duration_limit:
        cached = load_cached_timings(media_path, language, model_name)
        if cached:
            all_word_timings, srt_content = cached
            print(f"⚡ [Cache Hit] Réutilisation instantanée de la transcription Whisper ({len(all_word_timings)} mots).")
            chunks = group_words_into_chunks(all_word_timings, max_words=max_words)
            return chunks, srt_content

    input_audio_path = media_path
    temp_audio_file = None

    # For fast 3-second previews when full transcription isn't cached yet:
    # Extract audio snippet via ffmpeg in <0.1s to avoid processing the whole video
    if duration_limit and duration_limit > 0:
        from renderer import get_ffmpeg_path
        ffmpeg = get_ffmpeg_path()
        fd, temp_audio_file = tempfile.mkstemp(suffix="_preview.wav")
        os.close(fd)
        snippet_dur = duration_limit + 1.5
        cmd = [
            ffmpeg, "-y", "-ss", "0", "-t", str(snippet_dur),
            "-i", media_path, "-vn", "-ac", "1", "-ar", "16000",
            temp_audio_file
        ]
        res = subprocess.run(cmd, capture_output=True)
        if res.returncode == 0:
            input_audio_path = temp_audio_file

    try:
        model = get_whisper_model(model_name=model_name, device=device, compute_type=compute_type)

        dur_desc = f" ({duration_limit}s preview)" if duration_limit else ""
        print(f"[*] Transcription en cours{dur_desc}: '{media_path}' (Langue: {language or 'auto'}, beam_size=1 turbo)...")

        with _MODEL_LOCK:
            segments, info = model.transcribe(
                input_audio_path,
                language=language,
                beam_size=1,  # Turbo greedy decoding: ~2-3x faster than beam_size=5 with identical precision
                best_of=1,
                condition_on_previous_text=False,  # Prevents repetition loops and accelerates inference
                word_timestamps=True,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=300),
            )
            # Drain generator inside lock with live progress feedback
            total_audio_sec = getattr(info, "duration", 0.0) or 0.0
            segment_list = []
            for seg in segments:
                segment_list.append(seg)
                if progress_callback and total_audio_sec > 0:
                    progress_callback(seg.end, total_audio_sec)

        all_word_timings: List[WordTiming] = []
        srt_lines: List[str] = []

        for segment in segment_list:
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

        # Cache full transcriptions for immediate zero-latency reuse
        if use_cache and not duration_limit:
            save_cached_timings(media_path, language, model_name, all_word_timings, srt_content)

        print(f"[+] Transcription terminée: {len(all_word_timings)} mots, {len(chunks)} paquets.")
        return chunks, srt_content

    finally:
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.remove(temp_audio_file)
            except Exception:
                pass
