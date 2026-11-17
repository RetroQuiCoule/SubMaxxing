#!/usr/bin/env python3
"""
Submaxxing - The Ultimate Local, Free TikTok Subtitle Generator.
Generates dynamic, animated, bite-sized subtitles with highlight, bounce, and glow.
"""

import os
import sys
import argparse
import tempfile
from styles import PRESETS, SubStylePreset, chunks_to_ass
from chunker import srt_to_chunks
from renderer import (
    render_subtitles_to_video,
    render_transparent_overlay,
    get_video_info,
)


def main():
    parser = argparse.ArgumentParser(
        description="Submaxxing - Free Local TikTok / Shorts / Reels Animated Subtitles",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # 1. Transcribe MP4 directly with large-v3-turbo and Hormozi style (2 words/chunk):
  python submaxxing.py my_video.mp4 --transcribe --lang fr --style hormozi

  # 2. Use existing SRT, slice long phrases into 2 words, apply Neon Glow style:
  python submaxxing.py my_video.mp4 --srt subs.srt --style neon_glow

  # 3. Custom advanced styling:
  python submaxxing.py my_video.mp4 --srt subs.srt --highlight-color "#00FF66" --outline-width 6 --anim-scale 125 --anim-speed 80

  # 4. Generate transparent ProRes overlay for CapCut / Premiere:
  python submaxxing.py my_video.mp4 --srt subs.srt --overlay-only

Presets available:
  hormozi, mrbeast, neon_glow, clean_minimal, tiktok_bold, cyberpunk, fire_red
        """
    )

    parser.add_argument("video", help="Path to input 9:16 MP4 video")
    parser.add_argument("--srt", help="Path to existing SRT file (if already transcribed)")
    parser.add_argument("--transcribe", action="store_true", help="Run local Whisper transcription on video")
    parser.add_argument("--model", default="large-v3-turbo", help="Whisper model (default: large-v3-turbo)")
    parser.add_argument("--lang", default="fr", help="Language code ('fr', 'en', 'auto')")
    parser.add_argument("-w", "--words-per-chunk", type=int, default=2, help="Max words per subtitle chunk (1, 2, 3, or 4, default: 2)")
    parser.add_argument("-s", "--style", default="hormozi", choices=list(PRESETS.keys()), help="Style preset")
    parser.add_argument("--font", help="Override font name (e.g. 'Montserrat ExtraBold', 'Impact')")
    parser.add_argument("--font-size", type=int, help="Override font size (e.g. 82)")
    parser.add_argument("--highlight-color", help="Override highlight color (e.g. '#00FF66' or '#FFE600')")
    parser.add_argument("--primary-color", help="Override base text color (e.g. '#FFFFFF')")
    parser.add_argument("--outline-color", help="Override outline color (e.g. '#000000')")
    parser.add_argument("--outline-width", type=float, help="Override outline thickness (0 - 10)")
    parser.add_argument("--shadow-color", help="Override shadow color (e.g. '#000000')")
    parser.add_argument("--shadow-depth", type=float, help="Override shadow distance (0 - 8)")
    parser.add_argument("--glow", type=float, help="Glow blur intensity (0 - 10)")
    parser.add_argument("--animation", choices=["bounce", "pop", "fade", "none"], help="Override animation")
    parser.add_argument("--anim-speed", type=int, help="Animation snap duration in ms (e.g. 90)")
    parser.add_argument("--anim-scale", type=int, help="Animation peak scale percentage (e.g. 120)")
    parser.add_argument("--no-caps", action="store_true", help="Disable forced uppercase")
    parser.add_argument("--pos-y", type=int, help="Vertical margin from bottom in pixels (default ~560)")
    parser.add_argument("--overlay", action="store_true", help="Also generate transparent ProRes 4444 .mov overlay")
    parser.add_argument("--overlay-only", action="store_true", help="Only generate transparent ProRes overlay")
    parser.add_argument("--overlay-format", choices=["mov", "webm"], default="mov", help="Overlay format (mov or webm)")
    parser.add_argument("--ass-only", action="store_true", help="Only output the generated .ass subtitle file")
    parser.add_argument("--export-subs", "--keep-subs", dest="export_subs", action="store_true", help="Also export raw .srt and .ass subtitle files next to video (clean by default)")
    parser.add_argument("--no-cache", action="store_true", help="Force recalculating Whisper transcription, ignoring cache")
    parser.add_argument("--no-compress", action="store_true", help="Disable default web/TikTok video compression")
    parser.add_argument("--crf", type=int, default=22, help="Constant Rate Factor / Quality for compression (default: 22)")
    parser.add_argument("-o", "--output", help="Custom output video path")

    args = parser.parse_args()

    if not os.path.exists(args.video):
        print(f"[!] Error: Video file not found: {args.video}")
        sys.exit(1)

    base_name = os.path.splitext(args.video)[0]
    temp_ass_path = None
    if args.export_subs or args.ass_only:
        ass_path = f"{base_name}_submaxxing.ass"
    else:
        temp_fd, temp_ass_path = tempfile.mkstemp(suffix="_submaxxing.ass")
        os.close(temp_fd)
        ass_path = temp_ass_path

    try:
        # Step 1: Video Metadata
        print(f"[*] Reading video metadata: '{args.video}'...")
        vinfo = get_video_info(args.video)
        width = vinfo["width"]
        height = vinfo["height"]
        duration = vinfo["duration"]
        fps = vinfo["fps"]
        print(f"    Resolution: {width}x{height} | Duration: {duration:.2f}s | FPS: {fps:.2f}")

        # Step 2: Obtain Chunks (Whisper or SRT)
        if args.transcribe or not args.srt:
            if not args.srt:
                print("[*] No --srt provided, triggering local Whisper transcription...")
            from transcriber import transcribe_video
            chunks, srt_content = transcribe_video(
                media_path=args.video,
                model_name=args.model,
                language=None if args.lang == "auto" else args.lang,
                max_words=args.words_per_chunk,
                use_cache=not args.no_cache
            )
            if args.export_subs:
                generated_srt_path = f"{base_name}_transcribed.srt"
                with open(generated_srt_path, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                print(f"[+] Saved generated SRT to: '{generated_srt_path}'")
        else:
            if not os.path.exists(args.srt):
                print(f"[!] Error: SRT file not found: {args.srt}")
                sys.exit(1)
            print(f"[*] Parsing and slicing SRT: '{args.srt}' (max {args.words_per_chunk} words/chunk)...")
            chunks = srt_to_chunks(args.srt, max_words=args.words_per_chunk, is_file=True)
            print(f"[+] Sliced into {len(chunks)} digestible chunks.")

        if not chunks:
            print("[!] Error: No subtitles found or generated.")
            sys.exit(1)

        # Step 3: Configure Style Preset & Overrides
        preset = PRESETS.get(args.style, PRESETS["hormozi"])
        active_style = SubStylePreset(
            name=preset.name,
            font_name=args.font or preset.font_name,
            font_size=args.font_size or preset.font_size,
            primary_color=args.primary_color or preset.primary_color,
            highlight_color=args.highlight_color or preset.highlight_color,
            outline_color=args.outline_color or preset.outline_color,
            outline_width=args.outline_width if args.outline_width is not None else preset.outline_width,
            shadow_color=args.shadow_color or preset.shadow_color,
            shadow_depth=args.shadow_depth if args.shadow_depth is not None else preset.shadow_depth,
            blur=args.glow if args.glow is not None else preset.blur,
            all_caps=False if args.no_caps else preset.all_caps,
            animation=args.animation or preset.animation,
            anim_speed_ms=args.anim_speed or preset.anim_speed_ms,
            anim_scale=args.anim_scale or preset.anim_scale,
            margin_v=args.pos_y or preset.margin_v
        )

        # Step 4: Generate ASS
        print(f"[*] Generating ASS subtitles (Style: {active_style.name}, Animation: {active_style.animation})...")
        ass_content = chunks_to_ass(chunks, active_style, play_res_x=width, play_res_y=height)
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write(ass_content)
        if args.export_subs or args.ass_only:
            print(f"[+] ASS file created: '{ass_path}'")

        if args.ass_only:
            print("[+] --ass-only specified. Done!")
            return

        # Step 5: Render
        if args.overlay_only or args.overlay:
            ext = "mov" if args.overlay_format == "mov" else "webm"
            overlay_out = f"{base_name}_overlay.{ext}"
            render_transparent_overlay(
                ass_path=ass_path,
                output_path=overlay_out,
                duration=duration,
                width=width,
                height=height,
                fps=fps,
                format_type=args.overlay_format
            )
            if args.overlay_only:
                print("[+] Transparent overlay generated successfully!")
                return

        final_output = args.output or f"{base_name}_subbed.mp4"
        render_subtitles_to_video(
            video_path=args.video,
            ass_path=ass_path,
            output_path=final_output,
            use_gpu=True,
            compress=not args.no_compress,
            crf=args.crf
        )
        print(f"\n🎉 SUCCESS: Video rendered successfully to '{final_output}'!")

    finally:
        if temp_ass_path and os.path.exists(temp_ass_path):
            try:
                os.remove(temp_ass_path)
            except Exception:
                pass


if __name__ == "__main__":
    main()
