"""
Renderer module for Submaxxing.
Uses FFmpeg to burn .ass subtitles into MP4 with GPU NVENC acceleration,
or exports high-res transparent video overlays (ProRes 4444 .mov or WebM).
"""

import os
import shutil
import subprocess
import json
from typing import Optional, Dict, Any


def get_ffmpeg_path() -> str:
    """Finds the ffmpeg executable from PATH or common winget locations."""
    which_ffmpeg = shutil.which("ffmpeg")
    if which_ffmpeg:
        return which_ffmpeg

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    winget_pkg = os.path.join(
        local_app_data,
        "Microsoft", "WinGet", "Packages"
    )
    if os.path.exists(winget_pkg):
        for root, dirs, files in os.walk(winget_pkg):
            if "ffmpeg.exe" in files:
                return os.path.join(root, "ffmpeg.exe")

    return "ffmpeg"


def get_ffprobe_path() -> str:
    """Finds the ffprobe executable."""
    ffmpeg = get_ffmpeg_path()
    dir_name = os.path.dirname(ffmpeg)
    probe_name = "ffprobe.exe" if os.name == "nt" else "ffprobe"
    probe_path = os.path.join(dir_name, probe_name)
    if os.path.exists(probe_path):
        return probe_path

    which_probe = shutil.which("ffprobe")
    if which_probe:
        return which_probe
    return "ffprobe"


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
        stream = data.get("streams", [{}])[0]
        fmt = data.get("format", {})

        width = int(stream.get("width", 1080))
        height = int(stream.get("height", 1920))

        # Duration
        dur_str = stream.get("duration") or fmt.get("duration", "10.0")
        duration = float(dur_str)

        # FPS
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


def render_subtitles_to_video(
    video_path: str,
    ass_path: str,
    output_path: str,
    use_gpu: bool = True,
    duration_limit: Optional[float] = None
) -> str:
    """
    Burns ASS subtitles into video_path, outputting to output_path.
    Uses NVIDIA NVENC GPU acceleration if use_gpu=True.
    Optionally limits duration (e.g. for fast 3-second preview).
    """
    ffmpeg = get_ffmpeg_path()
    escaped_ass = escape_ass_path_for_ffmpeg(ass_path)

    # Base filter
    vf_arg = f"ass='{escaped_ass}'"

    dur_args = ["-t", str(duration_limit)] if duration_limit else []

    # Command with GPU NVENC
    if use_gpu:
        cmd = [
            ffmpeg, "-y",
            "-ss", "0"
        ] + dur_args + [
            "-i", video_path,
            "-vf", vf_arg,
            "-c:v", "h264_nvenc",
            "-preset", "p5",
            "-cq", "19",
            "-c:a", "copy",
            output_path
        ]
    else:
        cmd = [
            ffmpeg, "-y",
            "-ss", "0"
        ] + dur_args + [
            "-i", video_path,
            "-vf", vf_arg,
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "20",
            "-c:a", "copy",
            output_path
        ]

    limit_desc = f" ({duration_limit}s preview)" if duration_limit else ""
    print(f"[*] Rendering subtitled video{limit_desc} to '{output_path}'...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        if use_gpu:
            print("[!] GPU NVENC rendering failed, falling back to CPU (libx264)...")
            return render_subtitles_to_video(video_path, ass_path, output_path, use_gpu=False, duration_limit=duration_limit)
        else:
            raise RuntimeError(f"FFmpeg render error:\n{res.stderr}")

    print(f"[+] Render complete: '{output_path}'")
    return output_path


def render_transparent_overlay(
    ass_path: str,
    output_path: str,
    duration: float,
    width: int = 1080,
    height: int = 1920,
    fps: float = 30.0,
    format_type: str = "mov"  # "mov" (ProRes 4444) or "webm"
) -> str:
    """
    Generates a transparent video containing ONLY the animated subtitles.
    Ideal for dragging directly into CapCut / Premiere / DaVinci Resolve.
    """
    ffmpeg = get_ffmpeg_path()
    escaped_ass = escape_ass_path_for_ffmpeg(ass_path)

    if format_type.lower() == "mov":
        # Apple ProRes 4444 with Alpha channel
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={width}x{height}:r={fps}:d={duration}",
            "-vf", f"ass='{escaped_ass}',format=yuva444p10le",
            "-c:v", "prores_ks",
            "-profile:v", "4",
            "-vendor", "apl0",
            output_path
        ]
    else:
        # WebM VP9 with Alpha channel
        cmd = [
            ffmpeg, "-y",
            "-f", "lavfi",
            "-i", f"color=c=black@0.0:s={width}x{height}:r={fps}:d={duration}",
            "-vf", f"ass='{escaped_ass}',format=yuva420p",
            "-c:v", "libvpx-vp9",
            "-b:v", "0",
            "-crf", "20",
            output_path
        ]

    print(f"[*] Generating transparent overlay ({format_type.upper()}) to '{output_path}'...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg overlay error:\n{res.stderr}")

    print(f"[+] Overlay generation complete: '{output_path}'")
    return output_path
