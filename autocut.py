"""
Autocut & Smart Jumpcut module for Submaxxing.
Detects silences, stuttering/repetitions, and filler words from word-level Whisper timestamps.
Generates an interactive cut plan, re-syncs subtitle timings, and renders seamless jumpcuts via FFmpeg.
"""

import os
import re
import tempfile
import subprocess
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Set, Tuple, Dict, Any, Callable

from styles import WordTiming, SubChunk
from renderer import get_ffmpeg_path, detect_best_video_encoder, get_video_info


# Default filler words dictionary (French and English)
DEFAULT_FILLER_WORDS_FR = {
    "euh", "heu", "euhm", "hum", "bah", "ben", "genre", "du coup",
    "en fait", "tu vois", "tu sais", "voilà", "quoi"
}

DEFAULT_FILLER_WORDS_EN = {
    "uh", "um", "uhm", "er", "ah", "like", "you know", "basically", "actually"
}


@dataclass
class CutSegment:
    id: int
    start: float
    end: float
    duration: float
    reason: str  # "silence", "filler", "stutter"
    text: str    # Human-readable summary (e.g. "Silence (0.85s)", "Tic: 'euh'")
    enabled: bool = True

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3),
            "reason": self.reason,
            "text": self.text,
            "enabled": self.enabled
        }


@dataclass
class KeepSegment:
    start: float
    end: float
    duration: float

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start": round(self.start, 3),
            "end": round(self.end, 3),
            "duration": round(self.duration, 3)
        }


def _clean_token(w: str) -> str:
    """Strips punctuation and lowercases token for robust matching."""
    return re.sub(r"[^\w\s]", "", w).strip().lower()


def detect_cuts(
    word_timings: List[WordTiming],
    video_duration: float,
    min_silence_duration: float = 0.5,
    silence_padding: float = 0.08,
    detect_fillers: bool = True,
    detect_stutters: bool = True,
    custom_filler_words: Optional[Set[str]] = None
) -> List[CutSegment]:
    """
    Analyzes word timestamps and flags:
    1. Overly long silences (> min_silence_duration) while preserving natural acoustic breathing padding.
    2. Stutters (immediate repetition of words within short delay).
    3. Filler words / tics de langage.
    """
    raw_cuts: List[Tuple[float, float, str, str]] = []

    if not word_timings:
        # If no words detected at all, do not auto-cut the entire video away
        if video_duration > min_silence_duration:
            return [CutSegment(
                id=1,
                start=0.0,
                end=video_duration,
                duration=video_duration,
                reason="silence",
                text=f"Aucune parole détectée ({video_duration:.2f}s)",
                enabled=False
            )]
        return []

    filler_set = set(DEFAULT_FILLER_WORDS_FR) | set(DEFAULT_FILLER_WORDS_EN)
    if custom_filler_words:
        filler_set.update(w.strip().lower() for w in custom_filler_words if w.strip())

    # 1. Silence before first word
    first_start = word_timings[0].start
    if first_start > min_silence_duration:
        cut_end = max(0.0, first_start - silence_padding)
        if cut_end > 0.05:
            raw_cuts.append((0.0, cut_end, "silence", f"Silence début ({cut_end:.2f}s)"))

    # 2. Inter-word silences, stutters, and filler words
    for i in range(len(word_timings)):
        curr_w = word_timings[i]
        curr_tok = _clean_token(curr_w.word)

        # Check Stutter with next word
        if detect_stutters and i < len(word_timings) - 1:
            next_w = word_timings[i + 1]
            next_tok = _clean_token(next_w.word)
            gap_to_next = next_w.start - curr_w.end

            # Exact repetition or obvious stutter with delay < 0.4s
            if curr_tok and curr_tok == next_tok and 0 <= gap_to_next < 0.4:
                # Flag the first stuttered word for removal
                stutter_start = max(0.0, curr_w.start - 0.02)
                stutter_end = curr_w.end + min(0.05, gap_to_next / 2)
                raw_cuts.append((stutter_start, stutter_end, "stutter", f"Bégaiement: '{curr_w.word}'"))

        # Check Filler words
        if detect_fillers and curr_tok in filler_set:
            # Cut the filler word with slight margin
            f_start = max(0.0, curr_w.start - 0.02)
            f_end = curr_w.end + 0.02
            raw_cuts.append((f_start, f_end, "filler", f"Mot parasite: '{curr_w.word}'"))

        # Check Silence after this word until next word
        if i < len(word_timings) - 1:
            next_w = word_timings[i + 1]
            gap = next_w.start - curr_w.end
            if gap > min_silence_duration:
                cut_start = curr_w.end + silence_padding
                cut_end = next_w.start - silence_padding
                if cut_end - cut_start > 0.05:
                    raw_cuts.append((
                        cut_start,
                        cut_end,
                        "silence",
                        f"Silence ({cut_end - cut_start:.2f}s)"
                    ))

    # 3. Silence after last word
    last_end = word_timings[-1].end
    if video_duration > last_end + min_silence_duration:
        cut_start = last_end + silence_padding
        if video_duration - cut_start > 0.05:
            raw_cuts.append((
                cut_start,
                video_duration,
                "silence",
                f"Silence fin ({video_duration - cut_start:.2f}s)"
            ))

    # 4. Sort and merge overlapping or adjacent cuts
    raw_cuts.sort(key=lambda c: c[0])
    merged_cuts: List[CutSegment] = []

    for start, end, reason, desc in raw_cuts:
        start = max(0.0, round(start, 3))
        end = min(video_duration, round(end, 3))
        if end <= start:
            continue

        if not merged_cuts:
            merged_cuts.append(CutSegment(
                id=1,
                start=start,
                end=end,
                duration=round(end - start, 3),
                reason=reason,
                text=desc,
                enabled=True
            ))
            continue

        prev = merged_cuts[-1]
        # If cuts overlap or touch with less than 0.04s gap, merge them
        if start <= prev.end + 0.04:
            new_end = max(prev.end, end)
            prev.end = new_end
            prev.duration = round(new_end - prev.start, 3)
            # Combine reasons if different
            if reason != prev.reason:
                prev.reason = "mixed"
                prev.text = f"{prev.text} + {desc}"
        else:
            merged_cuts.append(CutSegment(
                id=len(merged_cuts) + 1,
                start=start,
                end=end,
                duration=round(end - start, 3),
                reason=reason,
                text=desc,
                enabled=True
            ))

    return merged_cuts


def compute_keep_segments(cuts: List[CutSegment], total_duration: float) -> List[KeepSegment]:
    """
    Inverts enabled cuts to produce contiguous segments to keep.
    Ensures no negative durations or micro-segments (< 0.08s).
    """
    active_cuts = sorted([c for c in cuts if c.enabled], key=lambda x: x.start)
    keep: List[KeepSegment] = []
    current_pos = 0.0

    for cut in active_cuts:
        if cut.start > current_pos + 0.08:
            keep.append(KeepSegment(
                start=round(current_pos, 3),
                end=round(cut.start, 3),
                duration=round(cut.start - current_pos, 3)
            ))
        current_pos = max(current_pos, cut.end)

    if current_pos < total_duration - 0.08:
        keep.append(KeepSegment(
            start=round(current_pos, 3),
            end=round(total_duration, 3),
            duration=round(total_duration - current_pos, 3)
        ))

    # Fallback to keep entire video if all cuts were somehow full duration
    if not keep and total_duration > 0.05:
        keep.append(KeepSegment(
            start=0.0,
            end=round(total_duration, 3),
            duration=round(total_duration, 3)
        ))

    return keep


def shift_word_timings_for_cuts(
    word_timings: List[WordTiming],
    cuts: List[CutSegment]
) -> List[WordTiming]:
    """
    Shifts word timestamps according to active cuts so subtitles stay
    frame-perfect with the shortened, dynamized video.
    """
    active_cuts = sorted([c for c in cuts if c.enabled], key=lambda x: x.start)
    if not active_cuts:
        return [WordTiming(w.word, w.start, w.end) for w in word_timings]

    shifted: List[WordTiming] = []

    for w in word_timings:
        # Check if word falls completely inside a cut
        inside_cut = False
        for c in active_cuts:
            if c.start <= w.start and w.end <= c.end:
                inside_cut = True
                break
        if inside_cut:
            continue

        # Calculate time removed before this word
        removed_before_start = 0.0
        removed_before_end = 0.0

        for c in active_cuts:
            if c.end <= w.start:
                removed_before_start += c.duration
                removed_before_end += c.duration
            elif c.start < w.start < c.end:
                # Word starts inside cut, shift start to cut end
                overlap = c.end - w.start
                removed_before_start += (c.duration - overlap)
                removed_before_end += c.duration
            elif w.start <= c.start and c.end <= w.end:
                # Cut is inside word
                removed_before_end += c.duration
            elif c.start < w.end <= c.end:
                removed_before_end += (w.end - c.start)

        new_start = max(0.0, round(w.start - removed_before_start, 3))
        new_end = max(new_start + 0.05, round(w.end - removed_before_end, 3))

        shifted.append(WordTiming(
            word=w.word,
            start=new_start,
            end=new_end
        ))

    # Ensure strictly monotonic timestamps
    for i in range(len(shifted) - 1):
        if shifted[i].end > shifted[i + 1].start:
            shifted[i].end = shifted[i + 1].start

    return shifted


def _has_audio_stream(file_path: str) -> bool:
    """Checks if the video file contains an audio stream."""
    from renderer import get_ffprobe_path
    ffprobe = get_ffprobe_path()
    try:
        cmd = [
            ffprobe, "-v", "error",
            "-select_streams", "a:0",
            "-show_entries", "stream=codec_type",
            "-of", "csv=p=0",
            file_path
        ]
        res = subprocess.run(cmd, capture_output=True, text=True, errors="replace")
        return bool(res.stdout.strip())
    except Exception:
        return True


def render_autocut_video(
    input_path: str,
    output_path: str,
    keep_segments: List[KeepSegment],
    use_nvenc: bool = True,
    normalize_audio: bool = True,
    progress_callback: Optional[Callable[[float, float], None]] = None
) -> str:
    """
    Uses FFmpeg to cut and concatenate keep_segments without desync.
    Handles videos both with and without audio streams gracefully.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"Fichier source introuvable: {input_path}")

    if not keep_segments:
        raise ValueError("Aucun segment à conserver (la vidéo serait vide).")

    ffmpeg = get_ffmpeg_path()
    codec, preset_args = detect_best_video_encoder() if use_nvenc else ("libx264", ["-preset", "fast", "-crf", "20"])

    has_audio = _has_audio_stream(input_path)
    total_cut_duration = sum(seg.duration for seg in keep_segments)

    # Build filter complex
    filter_parts = []
    n_segs = len(keep_segments)

    for i, seg in enumerate(keep_segments):
        s = seg.start
        e = seg.end
        filter_parts.append(f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS[v{i}];")
        if has_audio:
            filter_parts.append(f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS[a{i}];")

    if has_audio:
        concat_inputs = "".join(f"[v{i}][a{i}]" for i in range(n_segs))
        if normalize_audio:
            filter_parts.append(f"{concat_inputs}concat=n={n_segs}:v=1:a=1[outv][pre_a];[pre_a]loudnorm=I=-14:TP=-0.5:LRA=11[outa]")
        else:
            filter_parts.append(f"{concat_inputs}concat=n={n_segs}:v=1:a=1[outv][outa]")
    else:
        concat_inputs = "".join(f"[v{i}]" for i in range(n_segs))
        filter_parts.append(f"{concat_inputs}concat=n={n_segs}:v=1:a=0[outv]")

    filter_complex_str = "".join(filter_parts)
    stderr_log: List[str] = []

    cmd = [
        ffmpeg, "-y",
        "-i", input_path,
        "-filter_complex", filter_complex_str,
        "-map", "[outv]",
    ]
    if has_audio:
        cmd.extend(["-map", "[outa]"])

    cmd.extend(["-c:v", codec])
    cmd.extend(preset_args)

    if has_audio:
        cmd.extend(["-c:a", "aac", "-b:a", "192k"])

    cmd.extend([
        "-movflags", "+faststart",
        output_path
    ])

    print(f"[*] Rendu AutoCut ({n_segs} segments, durée finale: {total_cut_duration:.2f}s, audio: {has_audio})...")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        errors="replace"
    )

    time_regex = re.compile(r"time=(\d+):(\d+):(\d+\.\d+)")
    while True:
        line = proc.stderr.readline()
        if not line and proc.poll() is not None:
            break
        if line:
            stderr_log.append(line)
            if progress_callback and total_cut_duration > 0:
                match = time_regex.search(line)
                if match:
                    h, m, s = match.groups()
                    current_sec = int(h) * 3600 + int(m) * 60 + float(s)
                    progress_callback(min(current_sec, total_cut_duration), total_cut_duration)

    proc.wait()
    if proc.returncode != 0:
        err_summary = "".join(stderr_log[-20:])
        raise RuntimeError(f"Erreur FFmpeg AutoCut (code {proc.returncode}):\n{err_summary}")

    return output_path
