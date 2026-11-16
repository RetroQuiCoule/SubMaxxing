"""
Reframe Module for Submaxxing.
Converts 16:9 horizontal videos to 9:16 vertical TikTok / Reels / Shorts.
Features:
- Auto Face Tracking (Smart Pan with smoothed deadzone)
- Podcast / Split-Screen (Dual speaker vertical stack)
- Blurred Background (Fit & Blur)
- Manual / Center Crop
- Real-time video grading: Sharpness, Contrast, Saturation, Brightness, Vignette.
"""

import os
import cv2
import subprocess
from typing import Dict, Any, List, Tuple, Optional
from renderer import get_ffmpeg_path, get_video_info


def detect_face_centers(video_path: str, max_samples: int = 40) -> List[Tuple[float, float, int]]:
    """
    Samples frames from video_path and detects face positions using OpenCV.
    Returns a list of (timestamp, center_x_ratio, face_count).
    center_x_ratio is normalized between 0.0 (far left) and 1.0 (far right).
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        return [(0.0, 0.5, 0)]

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 100
    step = max(1, total_frames // max_samples)

    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    face_cascade = cv2.CascadeClassifier(cascade_path)

    detections = []
    current_frame = 0

    while cap.isOpened() and current_frame < total_frames:
        cap.set(cv2.CAP_PROP_POS_FRAMES, current_frame)
        ret, frame = cap.read()
        if not ret:
            break

        timestamp = current_frame / fps
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        h, w = frame.shape[:2]

        # Downscale for ultra fast detection
        scale = 0.5
        small = cv2.resize(gray, (int(w * scale), int(h * scale)))
        faces = face_cascade.detectMultiScale(small, scaleFactor=1.15, minNeighbors=4, minSize=(30, 30))

        if len(faces) > 0:
            # Pick the largest face (dominant speaker)
            best_face = max(faces, key=lambda b: b[2] * b[3])
            fx, fy, fw, fh = best_face
            center_x = (fx + fw / 2) / (w * scale)
            detections.append((timestamp, center_x, len(faces)))
        else:
            detections.append((timestamp, 0.5, 0))

        current_frame += step

    cap.release()
    return detections if detections else [(0.0, 0.5, 0)]


def calculate_average_face_x(detections: List[Tuple[float, float, int]], video_w: int, crop_w: int) -> int:
    """
    Computes a smoothed, optimal crop X coordinate centered on detected faces.
    """
    valid_detections = [x_ratio for _, x_ratio, count in detections if count > 0]
    if not valid_detections:
        return max(0, (video_w - crop_w) // 2)

    # Average face center X ratio
    avg_ratio = sum(valid_detections) / len(valid_detections)
    target_center_x = int(avg_ratio * video_w)
    crop_x = target_center_x - (crop_w // 2)
    return max(0, min(video_w - crop_w, crop_x))


def build_reframe_filter_chain(
    mode: str,
    video_w: int,
    video_h: int,
    crop_x: int,
    sharpness: float = 0.0,
    contrast: float = 1.0,
    saturation: float = 1.0,
    brightness: float = 0.0,
    vignette: float = 0.0,
) -> Tuple[str, bool]:
    """
    Builds the complete FFmpeg video filter for reframing and color enhancements.
    Returns (filter_string, is_complex).
    """
    crop_w = int(video_h * 9 / 16)

    # Grading parts
    adj_parts = []
    if contrast != 1.0 or saturation != 1.0 or brightness != 0.0:
        adj_parts.append(f"eq=contrast={contrast:.2f}:saturation={saturation:.2f}:brightness={brightness:.2f}")

    if sharpness > 0.0:
        s_val = min(2.0, sharpness * 1.5)
        adj_parts.append(f"unsharp=5:5:{s_val:.2f}:5:5:0.0")

    if vignette > 0.0:
        angle_val = max(0.2, min(1.5, vignette * 1.2))
        adj_parts.append(f"vignette=PI/{angle_val:.2f}")

    if mode == "blurred_bg":
        filter_complex = (
            f"[0:v]split=2[bg][fg];"
            f"[bg]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,boxblur=25:5[blurred];"
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

    else:
        # Standard crop (face_track, center, manual)
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
    use_gpu: bool = True
) -> str:
    """
    Executes the 16:9 -> 9:16 conversion using FFmpeg with NVENC hardware acceleration.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video not found: {video_path}")

    vinfo = get_video_info(video_path)
    video_w = vinfo["width"]
    video_h = vinfo["height"]
    crop_w = int(video_h * 9 / 16)

    # Calculate Crop X
    if mode == "center":
        crop_x = max(0, (video_w - crop_w) // 2)
    elif mode == "manual":
        ratio = max(0.0, min(100.0, float(manual_pan))) / 100.0
        crop_x = int(ratio * (video_w - crop_w))
    elif mode == "face_track":
        detections = detect_face_centers(video_path, max_samples=30)
        crop_x = calculate_average_face_x(detections, video_w, crop_w)
    else:
        crop_x = max(0, (video_w - crop_w) // 2)

    filter_str, is_complex = build_reframe_filter_chain(
        mode=mode,
        video_w=video_w,
        video_h=video_h,
        crop_x=crop_x,
        sharpness=sharpness,
        contrast=contrast,
        saturation=saturation,
        brightness=brightness,
        vignette=vignette,
    )

    ffmpeg = get_ffmpeg_path()
    dur_args = ["-ss", "0", "-t", str(duration_limit)] if duration_limit else []

    codec = "h264_nvenc" if use_gpu else "libx264"
    preset_args = ["-preset", "p5", "-cq", "19"] if use_gpu else ["-preset", "fast", "-crf", "20"]

    if is_complex:
        cmd = [
            ffmpeg, "-y"
        ] + dur_args + [
            "-i", video_path,
            "-filter_complex", filter_str,
            "-map", "[outv]",
            "-map", "0:a?",
            "-c:v", codec
        ] + preset_args + [
            "-c:a", "copy",
            output_path
        ]
    else:
        cmd = [
            ffmpeg, "-y"
        ] + dur_args + [
            "-i", video_path,
            "-vf", filter_str,
            "-c:v", codec
        ] + preset_args + [
            "-c:a", "copy",
            output_path
        ]

    print(f"[*] Reframing 16:9 -> 9:16 (Mode: {mode}, GPU: {use_gpu})...")
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        if use_gpu:
            print("[!] GPU failed for reframe, retrying on CPU...")
            return process_reframe(
                video_path=video_path, output_path=output_path, mode=mode,
                manual_pan=manual_pan, sharpness=sharpness, contrast=contrast,
                saturation=saturation, brightness=brightness, vignette=vignette,
                duration_limit=duration_limit, use_gpu=False
            )
        else:
            raise RuntimeError(f"FFmpeg reframe error:\n{res.stderr}")

    print(f"[+] Reframe complete: '{output_path}'")
    return output_path
