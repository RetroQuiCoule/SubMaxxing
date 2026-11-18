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
from chunker import group_words_into_chunks, merge_french_elisions, split_sentence_into_word_timings


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


def _get_cache_dir() -> str:
    """Returns the central cache directory for Submaxxing to keep media folders clean."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~\\AppData\\Local")
        cache_dir = os.path.join(base, "Submaxxing", "cache")
    else:
        cache_dir = os.path.expanduser("~/.cache/submaxxing")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _get_disk_cache_path(media_path: str) -> str:
    """Returns the persistent JSON cache file path in the centralized app cache directory."""
    cache_dir = _get_cache_dir()
    media_abs = os.path.abspath(media_path)
    base_name = os.path.splitext(os.path.basename(media_path))[0]
    safe_name = "".join(c for c in base_name if c.isalnum() or c in ("-", "_"))[:30] or "media"
    path_hash = hashlib.sha256(media_abs.encode("utf-8")).hexdigest()[:16]
    return os.path.join(cache_dir, f"{safe_name}_{path_hash}.json")


def get_cache_info() -> Dict[str, Any]:
    """Returns details on the current Whisper transcription cache and temporary files."""
    cache_dir = _get_cache_dir()
    files = []
    total_bytes = 0
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            if f.endswith(".json"):
                fp = os.path.join(cache_dir, f)
                try:
                    sz = os.path.getsize(fp)
                    total_bytes += sz
                    files.append(f)
                except Exception:
                    pass

    # Also count temp preview files
    td = tempfile.gettempdir()
    temp_files = []
    try:
        for f in os.listdir(td):
            if f.startswith("submaxxing_"):
                fp = os.path.join(td, f)
                try:
                    sz = os.path.getsize(fp)
                    total_bytes += sz
                    temp_files.append(f)
                except Exception:
                    pass
    except Exception:
        pass

    return {
        "cache_dir": cache_dir,
        "count": len(files),
        "temp_count": len(temp_files),
        "size_bytes": total_bytes,
        "size_mb": round(total_bytes / (1024 * 1024), 2),
    }


def clear_submaxxing_cache() -> int:
    """Clears all persistent Whisper transcriptions and temporary preview files."""
    global _TRANSCRIPTION_MEMORY_CACHE
    _TRANSCRIPTION_MEMORY_CACHE.clear()

    deleted = 0
    cache_dir = _get_cache_dir()
    if os.path.exists(cache_dir):
        for f in os.listdir(cache_dir):
            if f.endswith(".json"):
                fp = os.path.join(cache_dir, f)
                try:
                    os.remove(fp)
                    deleted += 1
                except Exception:
                    pass

    # Clean up temp preview files from system tempdir
    td = tempfile.gettempdir()
    try:
        for f in os.listdir(td):
            if f.startswith("submaxxing_"):
                fp = os.path.join(td, f)
                try:
                    os.remove(fp)
                    deleted += 1
                except Exception:
                    pass
    except Exception:
        pass

    # Also clean up any legacy in-workspace preview files if left over
    for legacy_f in ["web_preview.mp4", "web_preview.ass"]:
        if os.path.exists(legacy_f):
            try:
                os.remove(legacy_f)
                deleted += 1
            except Exception:
                pass

    return deleted


def load_cached_timings(media_path: str, language: Optional[str], model_name: str) -> Optional[Tuple[List[WordTiming], str]]:
    """Tries to retrieve pre-computed word timings from memory or disk cache."""
    key = _get_cache_key(media_path, language, model_name)
    if key in _TRANSCRIPTION_MEMORY_CACHE:
        return _TRANSCRIPTION_MEMORY_CACHE[key]

    cache_file = _get_disk_cache_path(media_path)
    candidates = [cache_file]

    # Legacy cache file path alongside media file (for backward compatibility and cleanup)
    base_dir = os.path.dirname(os.path.abspath(media_path))
    file_name = os.path.basename(media_path)
    legacy_file = os.path.join(base_dir, f".{file_name}.submaxxing_cache.json")
    if os.path.exists(legacy_file):
        candidates.append(legacy_file)

    for c_path in candidates:
        if os.path.exists(c_path):
            try:
                with open(c_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if data.get("cache_key") == key:
                    timings = [WordTiming(word=w["w"], start=w["s"], end=w["e"]) for w in data.get("words", [])]
                    srt_content = data.get("srt", "")
                    _TRANSCRIPTION_MEMORY_CACHE[key] = (timings, srt_content)

                    # If loaded from legacy location, migrate to central cache and clean up media folder
                    if c_path == legacy_file:
                        try:
                            save_cached_timings(media_path, language, model_name, timings, srt_content)
                            os.remove(legacy_file)
                        except Exception:
                            pass
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

    # Clean up legacy cache file if it exists in the media folder
    try:
        base_dir = os.path.dirname(os.path.abspath(media_path))
        file_name = os.path.basename(media_path)
        legacy_file = os.path.join(base_dir, f".{file_name}.submaxxing_cache.json")
        if os.path.exists(legacy_file):
            os.remove(legacy_file)
    except Exception:
        pass


def transcribe_to_words(
    media_path: str,
    model_name: str = "large-v3-turbo",
    language: Optional[str] = "fr",
    device: str = "auto",
    compute_type: str = "auto",
    use_cache: bool = True,
    duration_limit: Optional[float] = None,
    progress_callback: Optional[Callable[[float, float], None]] = None
) -> Tuple[List[WordTiming], str]:
    """
    Transcribes media_path directly and returns (all_word_timings, full_srt_string).
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
            return all_word_timings, srt_content

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

        for segment in segment_list:
            if segment.words:
                for w in segment.words:
                    cleaned_word = w.word.strip()
                    if cleaned_word:
                        w_start = float(w.start)
                        w_end = max(w_start + 0.05, float(w.end))
                        all_word_timings.append(WordTiming(
                            word=cleaned_word,
                            start=w_start,
                            end=w_end
                        ))
            else:
                seg_words = split_sentence_into_word_timings(segment.start, segment.end, segment.text)
                all_word_timings.extend(seg_words)

        # Merge French clitics (c', d', l', j', qu') & contractions so words are never fragmented
        all_word_timings = merge_french_elisions(all_word_timings)

        # Guarantee non-overlapping, strictly monotonic timestamps
        for i in range(len(all_word_timings) - 1):
            if all_word_timings[i].end > all_word_timings[i + 1].start:
                all_word_timings[i].end = all_word_timings[i + 1].start

        # Generate standard SRT
        srt_lines: List[str] = []
        chunks = group_words_into_chunks(all_word_timings, max_words=2)
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

        return all_word_timings, srt_content

    finally:
        if temp_audio_file and os.path.exists(temp_audio_file):
            try:
                os.remove(temp_audio_file)
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
    """
    all_word_timings, srt_content = transcribe_to_words(
        media_path=media_path,
        model_name=model_name,
        language=language,
        device=device,
        compute_type=compute_type,
        use_cache=use_cache,
        duration_limit=duration_limit,
        progress_callback=progress_callback
    )

    chunks = group_words_into_chunks(all_word_timings, max_words=max_words)
    print(f"[+] Transcription terminée: {len(all_word_timings)} mots, {len(chunks)} paquets.")
    return chunks, srt_content
