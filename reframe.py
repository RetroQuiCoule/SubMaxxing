"""
Reframe Module for Submaxxing.
Converts 16:9 horizontal videos to 9:16 vertical TikTok / Reels / Shorts.
Features:
- Dynamic Auto Face Tracking (Smart Pan with smoothed deadzone, multi-cascade detection and memory persistence)
- Podcast / Split-Screen (Dual speaker vertical stack)
- Ultra-Fast Blurred Background (Downscale-blur-upscale bokeh filter)
- Manual / Center Crop
- Real-time video grading: Sharpness, Contrast, Saturation, Brightness, Vignette.
- GPU NVENC hardware acceleration with adaptive presets for instant 3s previews.
"""

import os
import time
import tempfile
import cv2
import subprocess
from typing import Dict, Any, List, Tuple, Optional, Callable
from renderer import (
    get_ffmpeg_path,
    get_video_info,
    detect_best_video_encoder,
    run_ffmpeg_with_progress,
    escape_ass_path_for_ffmpeg,
)

_TRAJECTORY_CACHE: Dict[Tuple[str, int, float, Optional[float]], List[Tuple[float, float, bool]]] = {}
_CASCADE_FRONTAL = None
_CASCADE_PROFILE = None


def _get_cascades():
    global _CASCADE_FRONTAL, _CASCADE_PROFILE
    if _CASCADE_FRONTAL is None:
        _CASCADE_FRONTAL = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_alt2.xml")
    if _CASCADE_PROFILE is None:
        _CASCADE_PROFILE = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    return _CASCADE_FRONTAL, _CASCADE_PROFILE


def detect_face_in_frame(gray_small: Any) -> Optional[Tuple[int, int, int, int]]:
    """
    Detects the speaker face using frontal, profile, and flipped-profile classifiers.
    Returns (x, y, w, h) of the dominant face, or None.
    """
    c_front, c_prof = _get_cascades()

    # 1. Frontal & semi-profile face (alt2 is vastly superior for angled faces)
    faces = c_front.detectMultiScale(gray_small, scaleFactor=1.15, minNeighbors=3, minSize=(25, 25))
    if len(faces) > 0:
        return max(faces, key=lambda b: b[2] * b[3])

    # 2. Profile face (looking sideways)
    faces = c_prof.detectMultiScale(gray_small, scaleFactor=1.15, minNeighbors=3, minSize=(25, 25))
    if len(faces) > 0:
        return max(faces, key=lambda b: b[2] * b[3])

    # 3. Opposite profile face (flipped horizontally)
    flipped = cv2.flip(gray_small, 1)
    faces_f = c_prof.detectMultiScale(flipped, scaleFactor=1.15, minNeighbors=3, minSize=(25, 25))
    if len(faces_f) > 0:
        best_f = max(faces_f, key=lambda b: b[2] * b[3])
        w_img = gray_small.shape[1]
        fx, fy, fw, fh = best_f
        # Unflip coordinates back to original image space
        return (w_img - fx - fw, fy, fw, fh)

    return None


def detect_face_trajectory(
    video_path: str,
    fps: float,
    total_frames: int,
    duration_limit: Optional[float] = None,
    sample_rate: float = 8.0
) -> List[Tuple[float, float, bool]]:
    """
    Scans the video across time and extracts the speaker's horizontal center position.
    Returns a list of (timestamp, center_x_pixel, was_detected_bool).
    Features memory persistence so brief occlusions/blinks don't reset camera framing.
    Results are cached in memory for zero-latency subsequent operations.
    """
    if not os.path.exists(video_path):
        return [(0.0, 960.0, False)]

    try:
        stat = os.stat(video_path)
        cache_key = (os.path.abspath(video_path), stat.st_size, stat.st_mtime, duration_limit)
        if cache_key in _TRAJECTORY_CACHE:
            return _TRAJECTORY_CACHE[cache_key]
    except Exception:
        cache_key = None

    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return [(0.0, 960.0, False)]

    frames_to_scan = total_frames
    if duration_limit and duration_limit > 0:
        frames_to_scan = min(total_frames, int(fps * duration_limit))

    # Dense sampling rate: ~8 samples per second (every ~3-4 frames for 30fps)
    sample_step = max(1, int(round(fps / sample_rate)))

    v_w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    v_h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080

    target_w = 480
    scale = target_w / max(1, v_w)
    target_h = max(1, int(v_h * scale))

    trajectory: List[Tuple[float, float, bool]] = []
    current_frame = 0
    last_known_x = v_w / 2.0
    has_ever_detected = False

    while cap.isOpened() and current_frame < frames_to_scan:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = current_frame / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        small = cv2.resize(gray, (target_w, target_h))

        face = detect_face_in_frame(small)
        if face is not None:
            fx, fy, fw, fh = face
            cx = (fx + fw / 2.0) / scale
            last_known_x = cx
            has_ever_detected = True
            trajectory.append((timestamp, float(cx), True))
        else:
            trajectory.append((timestamp, float(last_known_x), False))

        current_frame += sample_step

    cap.release()

    # If first frames missed detection but a face was found later, backfill initial frames
    if has_ever_detected and trajectory:
        first_detected_x = next((x for _, x, det in trajectory if det), v_w / 2.0)
        backfilled = []
        found_first = False
        for t, x, det in trajectory:
            if det:
                found_first = True
            if not found_first:
                backfilled.append((t, first_detected_x, False))
            else:
                backfilled.append((t, x, det))
        trajectory = backfilled

    if not trajectory:
        trajectory = [(0.0, float(v_w / 2.0), False)]

    if cache_key:
        _TRAJECTORY_CACHE[cache_key] = trajectory

    return trajectory


def generate_smoothed_camera_pan(
    trajectory: List[Tuple[float, float, bool]],
    video_w: int,
    video_h: int,
    fps: float,
    total_frames: int,
    deadzone_ratio: float = 0.04,
    smooth_factor: float = 0.65
) -> List[Tuple[float, int]]:
    """
    Computes cinematic gimbal camera panning positions (x coordinate) for every frame.
    Applies deadzone to avoid fidgeting and exponential smoothing for organic movement.
    Guarantees crop x stays strictly within [0, video_w - crop_w].
    """
    crop_w = int(video_h * 9 / 16)
    max_crop_x = max(0, video_w - crop_w)

    any_detected = any(det for _, _, det in trajectory)
    if not any_detected:
        center_x = max(0, (video_w - crop_w) // 2)
        return [(f / fps, center_x) for f in range(total_frames)]

    deadzone = crop_w * deadzone_ratio
    first_face_x = trajectory[0][1]
    first_target = max(0.0, min(float(max_crop_x), first_face_x - crop_w / 2.0))
    cur_cam_x = first_target

    smoothed_keyframes: List[Tuple[float, int]] = []
    for t, face_cx, det in trajectory:
        target_x = max(0.0, min(float(max_crop_x), face_cx - crop_w / 2.0))
        diff = target_x - cur_cam_x
        if abs(diff) > deadzone:
            cur_cam_x += diff * smooth_factor
        cur_cam_x = max(0.0, min(float(max_crop_x), cur_cam_x))
        smoothed_keyframes.append((t, int(round(cur_cam_x))))

    # Interpolate to every single frame of the video
    frame_pans: List[Tuple[float, int]] = []
    num_keys = len(smoothed_keyframes)

    key_idx = 0
    for f in range(total_frames):
        t = f / fps
        if num_keys == 1 or t <= smoothed_keyframes[0][0]:
            crop_x = smoothed_keyframes[0][1]
        elif t >= smoothed_keyframes[-1][0]:
            crop_x = smoothed_keyframes[-1][1]
        else:
            while key_idx < num_keys - 1 and smoothed_keyframes[key_idx + 1][0] < t:
                key_idx += 1
            t0, x0 = smoothed_keyframes[key_idx]
            t1, x1 = smoothed_keyframes[min(num_keys - 1, key_idx + 1)]
            if t1 > t0:
                alpha = (t - t0) / (t1 - t0)
                crop_x = int(round(x0 + alpha * (x1 - x0)))
            else:
                crop_x = x0

        crop_x = max(0, min(max_crop_x, crop_x))
        frame_pans.append((t, crop_x))

    return frame_pans


def write_sendcmd_pan_script(frame_pans: List[Tuple[float, int]], script_path: str) -> str:
    """
    Writes an FFmpeg sendcmd script formatting: '<time> crop x <x>;'
    Optimized: emits a command at frame 0 and whenever x changes.
    """
    lines = []
    prev_x = None
    for t, x in frame_pans:
        if prev_x is None or x != prev_x:
            lines.append(f"{t:.3f} crop x {x};")
            prev_x = x

    if not lines and frame_pans:
        lines.append(f"0.000 crop x {frame_pans[0][1]};")

    with open(script_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return script_path


def build_reframe_filter_chain(
    mode: str,
    video_w: int,
    video_h: int,
    crop_x: int = 0,
    sendcmd_path: Optional[str] = None,
    sharpness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    brightness: float = 0.0,
    vignette: float = 0.0,
) -> Tuple[str, bool]:
    """
    Builds the complete FFmpeg video filter for reframing and color enhancements.
    Supports dynamic pan via sendcmd, bokeh blurred background, and grading.
    Returns (filter_string, is_complex).
    """
    crop_w = int(video_h * 9 / 16)

    # Grading parts
    adj_parts = []
    if contrast != 1.0 or saturation != 1.0 or brightness != 0.0:
        adj_parts.append(f"eq=contrast={contrast:.2f}:saturation={saturation:.2f}:brightness={brightness:.2f}")

    if sharpness > 0.0:
        s_val = min(3.5, sharpness * 3.0)
        adj_parts.append(f"unsharp=7:7:{s_val:.2f}:7:7:0.0")

    if vignette > 0.0:
        v_ratio = max(0.01, min(1.0, float(vignette)))
        div = 6.5 - (v_ratio * 4.4)
        adj_parts.append(f"vignette=a=PI/{div:.2f}:aspect=9/16")

    if mode == "blurred_bg":
        # Ultra-optimized bokeh blur: scales bg to 270x480, applies gentle blur, then scales back up
        filter_complex = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale=270:480:force_original_aspect_ratio=increase,crop=270:480,boxblur=8:2,scale=1080:1920:flags=bicubic[blurred];"
            f"[fg]scale=1080:-1[crisp];"
            f"[blurred][crisp]overlay=(W-w)/2:(H-h)/2"
        )
        if adj_parts:
            filter_complex += f"[base];[base]{','.join(adj_parts)}[outv]"
        else:
            filter_complex += "[outv]"
        return filter_complex, True

    elif mode == "split_screen":
        left_crop_x = max(0, int(video_w * 0.15))
        right_crop_x = min(video_w - crop_w, int(video_w * 0.55))
        filter_complex = (
            f"[0:v]split=2[top_in][bot_in];"
            f"[top_in]crop={crop_w}:{video_h}:{left_crop_x}:0,scale=1080:960[top];"
            f"[bot_in]crop={crop_w}:{video_h}:{right_crop_x}:0,scale=1080:960[bottom];"
            f"[top][bottom]vstack=inputs=2"
        )
        if adj_parts:
            filter_complex += f"[base];[base]{','.join(adj_parts)}[outv]"
        else:
            filter_complex += "[outv]"
        return filter_complex, True

    elif mode == "face_track" and sendcmd_path:
        esc_cmd = escape_ass_path_for_ffmpeg(sendcmd_path)
        filters = [f"sendcmd=f='{esc_cmd}',crop=w={crop_w}:h={video_h}:x=0:y=0,scale=1080:1920"]
        if adj_parts:
            filters.extend(adj_parts)
        return ",".join(filters), False

    else:
        # Standard static crop (center, manual, or face_track fallback)
        filters = [f"crop={crop_w}:{video_h}:{crop_x}:0,scale=1080:1920"]
        if adj_parts:
            filters.extend(adj_parts)
        return ",".join(filters), False


def process_reframe(
    video_path: str,
    output_path: str,
    mode: str = "face_track",
    manual_pan: int = 50,
    sharpness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    brightness: float = 0.0,
    vignette: float = 0.0,
    duration_limit: Optional[float] = None,
    use_gpu: bool = True,
    progress_callback: Optional[Callable[[float, float, float, str], None]] = None
) -> str:
    """
    Executes the 16:9 -> 9:16 conversion using FFmpeg with NVENC hardware acceleration.
    In 'face_track' mode, dynamically pans the 9:16 frame smoothly following the speaker.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    vinfo = get_video_info(video_path)
    video_w = vinfo["width"]
    video_h = vinfo["height"]
    fps = vinfo.get("fps", 30.0)
    crop_w = int(video_h * 9 / 16)

    cmd_script_path = None

    try:
        # Calculate Framing & Pan Coordinates
        if mode == "center":
            crop_x = max(0, (video_w - crop_w) // 2)
        elif mode == "manual":
            ratio = max(0.0, min(100.0, float(manual_pan))) / 100.0
            crop_x = int(ratio * (video_w - crop_w))
        elif mode == "face_track":
            effective_dur = duration_limit if duration_limit else vinfo.get("duration", 10.0)
            frames_count = max(1, int(round(fps * effective_dur)))

            print(f"[*] Analyzing face trajectory across {effective_dur:.1f}s ({frames_count} frames)...")
            trajectory = detect_face_trajectory(
                video_path=video_path,
                fps=fps,
                total_frames=frames_count,
                duration_limit=duration_limit
            )

            frame_pans = generate_smoothed_camera_pan(
                trajectory=trajectory,
                video_w=video_w,
                video_h=video_h,
                fps=fps,
                total_frames=frames_count
            )

            cmd_script_path = os.path.join(
                tempfile.gettempdir(),
                f"submaxxing_pan_{os.getpid()}_{int(time.time() * 1000)}.cmd"
            )
            write_sendcmd_pan_script(frame_pans, cmd_script_path)
            crop_x = frame_pans[0][1] if frame_pans else max(0, (video_w - crop_w) // 2)
            print(f"[+] Dynamic pan script generated: {len(frame_pans)} frames tracked.")
        else:
            crop_x = max(0, (video_w - crop_w) // 2)

        filter_str, is_complex = build_reframe_filter_chain(
            mode=mode,
            video_w=video_w,
            video_h=video_h,
            crop_x=crop_x,
            sendcmd_path=cmd_script_path if mode == "face_track" else None,
            sharpness=sharpness,
            contrast=contrast,
            saturation=saturation,
            brightness=brightness,
            vignette=vignette,
        )

        ffmpeg = get_ffmpeg_path()
        dur_args = ["-t", str(duration_limit)] if duration_limit else []

        if use_gpu:
            codec, base_preset = detect_best_video_encoder()
            if codec == "h264_nvenc":
                preset_args = ["-preset", "p1" if duration_limit else "p4", "-cq", "19", "-spatial-aq", "1"]
            elif codec == "libx264":
                preset_args = ["-preset", "ultrafast" if duration_limit else "fast", "-crf", "20"]
            else:
                preset_args = base_preset
        else:
            codec = "libx264"
            preset_args = ["-preset", "ultrafast" if duration_limit else "fast", "-crf", "20"]

        if is_complex:
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
            ] + dur_args + [
                "-filter_complex", filter_str,
                "-map", "[outv]",
                "-map", "0:a?",
                "-c:v", codec,
            ] + preset_args + [
                "-threads", "0",
                "-c:a", "copy",
                output_path
            ]
        else:
            cmd = [
                ffmpeg, "-y",
                "-i", video_path,
            ] + dur_args + [
                "-vf", filter_str,
                "-c:v", codec,
            ] + preset_args + [
                "-threads", "0",
                "-c:a", "copy",
                output_path
            ]

        limit_desc = f" ({duration_limit}s preview)" if duration_limit else ""
        print(f"[*] Reframing 16:9 -> 9:16{limit_desc} (Mode: {mode}, via {codec})...")

        total_dur = duration_limit if duration_limit else vinfo.get("duration", 10.0)

        try:
            run_ffmpeg_with_progress(
                cmd=cmd,
                duration=total_dur,
                progress_callback=progress_callback,
                desc=f"Reframe ({codec})"
            )
        except Exception as e:
            if use_gpu and codec != "libx264":
                print(f"[!] {codec} failed for reframe ({e}), retrying on CPU (libx264)...")
                return process_reframe(
                    video_path=video_path, output_path=output_path, mode=mode,
                    manual_pan=manual_pan, sharpness=sharpness, contrast=contrast,
                    saturation=saturation, brightness=brightness, vignette=vignette,
                    duration_limit=duration_limit, use_gpu=False,
                    progress_callback=progress_callback
                )
            else:
                raise

        print(f"[+] Reframe complete: '{output_path}'")
        return output_path

    finally:
        if cmd_script_path and os.path.exists(cmd_script_path):
            try:
                os.remove(cmd_script_path)
            except Exception:
                pass
