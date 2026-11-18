"""
Renderer module for Submaxxing.
Uses FFmpeg to burn .ass subtitles into MP4 with GPU NVENC acceleration,
or exports high-res transparent video overlays (ProRes 4444 .mov or WebM).
Optimized for ultra-fast previews and maximum export throughput.
"""

import os
import shutil
import subprocess
import json
import threading
from typing import Optional, Dict, Any, Tuple, Callable

_CACHED_FFMPEG_PATH: Optional[str] = None
_CACHED_FFPROBE_PATH: Optional[str] = None
_SUPPORTED_HW_ENCODER: Optional[str] = None


def get_ffmpeg_path() -> str:
    """Finds the ffmpeg executable from PATH or common winget locations with caching."""
    global _CACHED_FFMPEG_PATH
    if _CACHED_FFMPEG_PATH:
        return _CACHED_FFMPEG_PATH

    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        _CACHED_FFMPEG_PATH = which_ffmpeg
        return which_ffmpeg

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    winget_pkg = os.path.join(
        local_app_data,
        "Microsoft", "WinGet", "Packages"
    )
    if os.path.exists(winget_pkg):
        for root, dirs, files in os.walk(winget_pkg):
            if "ffmpeg.exe" in files:
                p = os.path.join(root, "ffmpeg.exe")
                _CACHED_FFMPEG_PATH = p
                return p

    _CACHED_FFMPEG_PATH = "ffmpeg"
    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Finds the ffprobe executable with caching."""
    global _CACHED_FFPROBE_PATH
    if _CACHED_FFPROBE_PATH:
        return _CACHED_FFPROBE_PATH

    ffmpeg = get_ffmpeg_path()
    dir_name = os.path.dirname(ffmpeg)
    probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    probe_path = os.path.join(dir_name, probe_name)
    if os.path.exists(probe_path):
        _CACHED_FFPROBE_PATH = probe_path
        return probe_path

    which_probe = shutil.which("ffprobe")
    if which_probe:
        _CACHED_FFPROBE_PATH = which_probe
        return which_probe

    _CACHED_FFPROBE_PATH = "ffprobe"
    return "ffprobe"


def detect_best_video_encoder() -> Tuple[str, list]:
    """
    Detects the best available hardware encoder (NVIDIA NVENC, QuickSync, AMF, or CPU libx264).
    Returns (codec_name, default_preset_args).
    """
    global _SUPPORTED_HW_ENCODER
    if _SUPPORTED_HW_ENCODER:
        return _SUPPORTED_HW_ENCODER

    ffmpeg = get_ffmpeg_path()
    try:
        res = subprocess.run([ffmpeg, "-encoders"], capture_output=True, text=True, errors="replace")
        output = res.stdout
        if "h264_nvenc" in output:
            # Test a dummy 1-frame NVENC encode to be 100% sure the driver initializes cleanly (NVENC requires >= 144x144)
            test_cmd = [
                ffmpeg, "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.04",
                "-c:v", "h264_nvenc", "-f", "null", "-"
            ]
            t_res = subprocess.run(test_cmd, capture_output=True)
            if t_res.returncode == 0:
                _SUPPORTED_HW_ENCODER = ("h264_nvenc", ["-preset", "p4", "-cq", "19", "-spatial-aq", "1"])
                return _SUPPORTED_HW_ENCODER

        if "h264_qsv" in output:
            _SUPPORTED_HW_ENCODER = ("h264_qsv", ["-preset", "fast", "-global_quality", "20"])
            return _SUPPORTED_HW_ENCODER

        if "h264_amf" in output:
            _SUPPORTED_HW_ENCODER = ("h264_amf", ["-quality", "speed"])
            return _SUPPORTED_HW_ENCODER
    except Exception:
        pass

    _SUPPORTED_HW_ENCODER = ("libx264", ["-preset", "fast", "-crf", "20"])
    return _SUPPORTED_HW_ENCODER


def get_video_info(video_path: str) -> Dict[str, Any]:
    """Retrieves video duration, width, height, and FPS using ffprobe."""
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe,
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,r_frame_rate,duration:format=duration",
        "-of", "json",
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, check=True)
        data = json.loads(res.stdout)
        streams = data.get("streams", [])
        stream = streams[0] if streams else {}
        fmt = data.get("format", {})

        width = int(stream.get("width", 1080))
        height = int(stream.get("height", 1920))

        dur_str = stream.get("duration") or fmt.get("duration", "10.0")
        duration = float(dur_str)

        r_fps = stream.get("r_frame_rate", "30/1")
        if "/" in r_fps:
            num, den = r_fps.split("/")
            fps = float(num) / float(den) if float(den) != 0 else 30.0
        else:
            fps = float(r_fps)

        return {"width": width, "height": height, "duration": duration, "fps": fps}
    except Exception as e:
        print(f"[!] Warning: Could not ffprobe video info ({e}), defaulting to 1080x1920 30fps.")
        return {"width": 1080, "height": 1920, "duration": 30.0, "fps": 30.0}


def escape_ass_path_for_ffmpeg(ass_path: str) -> str:
    r"""
    Escapes windows backslashes and drive colons for FFmpeg filter syntax.
    Example: 'C:\path\subs.ass' -> 'C\\:/path/subs.ass'
    """
    p = os.path.abspath(ass_path)
    p = p.replace('\\', '/')
    p = p.replace(':', r'\:')
    return p


def run_ffmpeg_with_progress(
    cmd: list,
    duration: Optional[float] = None,
    progress_callback: Optional[Callable[[float, float, float, str], None]] = None,
    desc: str = "Encoding"
) -> None:
    """
    Executes an FFmpeg command with real-time stdout progress monitoring and thread-safe stderr capture.
    progress_callback receives (percent, current_seconds, total_seconds, speed).
    """
    # Insert progress options right after ffmpeg executable
    full_cmd = [cmd[0], "-stats_period", "0.2", "-progress", "pipe:1"] + cmd[1:]

    proc = subprocess.Popen(
        full_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        errors="replace"
    )

    stderr_lines = []
    def _read_stderr():
        try:
            for line in iter(proc.stderr.readline, ''):
                if line:
                    stderr_lines.append(line)
                    if len(stderr_lines) > 200:
                        stderr_lines.pop(0)
        except Exception:
            pass

    t_err = threading.Thread(target=_read_stderr, daemon=True)
    t_err.start()

    cur_sec = 0.0
    speed = "1.0x"

    try:
        for line in iter(proc.stdout.readline, ''):
            line = line.strip()
            if line.startswith("out_time="):
                val = line.split("=", 1)[1].strip()
                parts = val.split(":")
                if len(parts) == 3:
                    try:
                        cur_sec = float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
                        if duration and duration > 0:
                            pct = min(99.0, (cur_sec / duration) * 100.0)
                        else:
                            pct = 50.0
                        if progress_callback:
                            progress_callback(pct, cur_sec, duration or 0.0, speed)
                    except ValueError:
                        pass
            elif line.startswith("speed="):
                speed = line.split("=", 1)[1].strip()
    except Exception:
        pass

    proc.wait()
    t_err.join(timeout=1.0)

    if proc.returncode != 0:
        err_msg = "".join(stderr_lines)
        raise RuntimeError(f"FFmpeg {desc} error (exit code {proc.returncode}):\n{err_msg}")

    if progress_callback and duration and duration > 0:
        progress_callback(100.0, duration, duration, speed)


def has_audio_stream(video_path: str) -> bool:
    """Checks if the video/audio file contains an audio stream."""
    ffprobe = get_ffprobe_path()
    cmd = [
        ffprobe, "-v", "error",
        "-select_streams", "a:0",
        "-show_entries", "stream=codec_type",
        "-of", "csv=p=0",
        video_path
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True)
        return "audio" in res.stdout.lower()
    except Exception:
        return False


def render_subtitles_to_video(
    video_path: str,
    ass_path: str,
    output_path: str,
    use_gpu: bool = True,
    compress: bool = True,
    crf: int = 22,
    duration_limit: Optional[float] = None,
    progress_callback: Optional[Callable[[float, float, float, str], None]] = None,
    normalize_audio: bool = False
) -> str:
    """
    Burns ASS subtitles into video_path, outputting to output_path.
    Uses NVIDIA NVENC GPU acceleration when available, with ultra-fast presets for previews.
    Applies smart TikTok/Web video compression by default (CRF/CQ 22, Faststart, AAC 192k, YUV420P).
    Tracks real encoding progress via progress_callback.
    """
    ffmpeg = get_ffmpeg_path()
    escaped_ass = escape_ass_path_for_ffmpeg(ass_path)
    vf_arg = f"ass='{escaped_ass}'"

    dur_args = ["-t", str(duration_limit)] if duration_limit else []
    is_preview = bool(duration_limit)

    if use_gpu:
        codec, base_preset = detect_best_video_encoder()
        if codec == "h264_nvenc":
            if is_preview:
                preset_args = ["-preset", "p1", "-cq", str(crf)]
            else:
                preset_args = [
                    "-preset", "p4",
                    "-cq", str(crf),
                    "-b:v", "0",
                    "-maxrate", "12M",
                    "-bufsize", "24M",
                    "-spatial-aq", "1",
                    "-profile:v", "high"
                ] if compress else ["-preset", "p4", "-cq", "19", "-spatial-aq", "1"]
        elif codec == "libx264":
            if is_preview:
                preset_args = ["-preset", "ultrafast", "-crf", str(crf)]
            else:
                preset_args = [
                    "-preset", "fast",
                    "-crf", str(crf),
                    "-maxrate", "12M",
                    "-bufsize", "24M",
                    "-profile:v", "high"
                ] if compress else ["-preset", "fast", "-crf", "20"]
        else:
            preset_args = base_preset
    else:
        codec = "libx264"
        if is_preview:
            preset_args = ["-preset", "ultrafast", "-crf", str(crf)]
        else:
            preset_args = [
                "-preset", "fast",
                "-crf", str(crf),
                "-maxrate", "12M",
                "-bufsize", "24M",
                "-profile:v", "high"
            ] if compress else ["-preset", "fast", "-crf", "20"]

    # Extra optimization args for web & social platforms (TikTok, Reels, Shorts)
    extra_opts = ["-pix_fmt", "yuv420p"]
    if not is_preview and compress:
        extra_opts += ["-movflags", "+faststart"]

    # Audio handling: AAC 192k for clean compression; copy for quick preview
    # If normalize_audio is enabled, apply broadcast EBU R128 loudnorm (-14 LUFS, -0.5 dB True Peak)
    if is_preview:
        audio_args = ["-c:a", "copy"]
    elif normalize_audio and has_audio_stream(video_path):
        audio_args = ["-af", "loudnorm=I=-14:TP=-0.5:LRA=11", "-c:a", "aac", "-b:a", "192k"]
    else:
        audio_args = ["-c:a", "aac", "-b:a", "192k"]

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
    ] + dur_args + [
        "-vf", vf_arg,
        "-c:v", codec,
    ] + preset_args + extra_opts + [
        "-threads", "0",
    ] + audio_args + [
        output_path
    ]

    limit_desc = f" ({duration_limit}s preview, preset {preset_args[1]})" if duration_limit else (" [Compressed]" if compress else "")
    print(f"[*] Rendering subtitled video{limit_desc} via {codec} to '{output_path}'...")

    vinfo = get_video_info(video_path)
    total_dur = duration_limit if duration_limit else vinfo.get("duration", 10.0)

    try:
        run_ffmpeg_with_progress(
            cmd=cmd,
            duration=total_dur,
            progress_callback=progress_callback,
            desc=f"Subtitles Render ({codec})"
        )
    except Exception as e:
        if use_gpu and codec != "libx264":
            print(f"[!] {codec} rendering failed ({e}), falling back to CPU (libx264)...")
            return render_subtitles_to_video(
                video_path=video_path,
                ass_path=ass_path,
                output_path=output_path,
                use_gpu=False,
                compress=compress,
                crf=crf,
                duration_limit=duration_limit,
                progress_callback=progress_callback
            )
        else:
            raise

    print(f"[+] Render complete: '{output_path}'")
    return output_path


def compress_video(
    video_path: str,
    output_path: Optional[str] = None,
    crf: int = 22,
    max_bitrate: str = "12M",
    use_gpu: bool = True,
    progress_callback: Optional[Callable[[float, float, float, str], None]] = None
) -> str:
    """
    Compresses any input video into a web-optimized MP4 (H.264 high profile, Faststart, AAC audio).
    """
    if not output_path:
        base, ext = os.path.splitext(video_path)
        output_path = f"{base}_compressed.mp4"

    ffmpeg = get_ffmpeg_path()
    vinfo = get_video_info(video_path)
    total_dur = vinfo.get("duration", 10.0)

    if use_gpu:
        codec, _ = detect_best_video_encoder()
        if codec == "h264_nvenc":
            enc_args = ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", str(crf), "-b:v", "0", "-maxrate", max_bitrate, "-bufsize", "24M", "-spatial-aq", "1", "-profile:v", "high"]
        else:
            enc_args = ["-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-maxrate", max_bitrate, "-bufsize", "24M", "-profile:v", "high"]
    else:
        enc_args = ["-c:v", "libx264", "-preset", "fast", "-crf", str(crf), "-maxrate", max_bitrate, "-bufsize", "24M", "-profile:v", "high"]

    cmd = [
        ffmpeg, "-y",
        "-i", video_path,
    ] + enc_args + [
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        "-b:a", "192k",
        "-threads", "0",
        output_path
    ]

    print(f"[*] Compressing video to '{output_path}'...")
    run_ffmpeg_with_progress(cmd, duration=total_dur, progress_callback=progress_callback, desc="Compressing")
    return output_path


def render_transparent_overlay(
    ass_path: str,
    output_path: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30.0,
    format_type: str = "mov",  # "mov" (ProRes 4444) or "webm"
    progress_callback: Optional[Callable[[float, float, float, str], None]] = None
) -> str:
    """
    Generates a transparent video containing ONLY the animated subtitles.
    Ideal for dragging directly into CapCut / Premiere / DaVinci Resolve.
    Highly optimized for multi-threaded VP9 and ProRes execution.
    """
    ffmpeg = get_ffmpeg_path()
    escaped_ass = escape_ass_path_for_ffmpeg(ass_path)

    if format_type.lower() == "mov":
        # Apple ProRes 4444 with Alpha channel and multi-threading
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={width}x{height}:r={fps}:d={duration}",
            "-vf", f"ass='{escaped_ass}',format=yuva444p10le",
            "-c:v", "prores_ks",
            "-profile:v", "4",
            "-vendor", "apl0",
            "-threads", "0",
            output_path
        ]
    else:
        # WebM VP9 with Alpha channel - optimized with row-mt and parallel tiles for 5-10x speedup
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={width}x{height}:r={fps}:d={duration}",
            "-vf", f"ass='{escaped_ass}',format=yuva420p",
            "-c:v", "libvpx-vp9",
            "-b:v", "0",
            "-crf", "24",
            "-threads", "0",
            "-row-mt", "1",
            "-speed", "4",
            "-tile-columns", "2",
            "-frame-parallel", "1",
            output_path
        ]

    print(f"[*] Generating transparent overlay ({format_type.upper()}) to '{output_path}'...")
    run_ffmpeg_with_progress(
        cmd=cmd,
        duration=duration,
        progress_callback=progress_callback,
        desc=f"Overlay ({format_type.upper()})"
    )

    print(f"[+] Overlay generation complete: '{output_path}'")
    return output_path
