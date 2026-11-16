"""
Styles and ASS subtitle generation for Submaxxing.
Generates Advanced SubStation Alpha (.ass) files tailored for 9:16 TikTok / Reels / Shorts.
Supports full custom styling: colors, fonts, outline, shadow, glow, and animations (bounce, pop, fade).
"""

from dataclasses import dataclass
from typing import List, Tuple, Optional


def hex_to_ass_color(hex_color: str, alpha: int = 0) -> str:
    """
    Converts #RRGGBB or RRGGBB to ASS &HAABBGGRR& format.
    ASS colors are in BGR order with optional leading alpha (00 = opaque, FF = fully transparent).
    """
    hex_color = hex_color.lstrip('#')
    if len(hex_color) == 6:
        r = hex_color[0:2]
        g = hex_color[2:4]
        b = hex_color[4:6]
        return f"&H{alpha:02X}{b}{g}{r}&"
    elif len(hex_color) == 8:
        r = hex_color[0:2]
        g = hex_color[2:4]
        b = hex_color[4:6]
        a = hex_color[6:8]
        return f"&H{a}{b}{g}{r}&"
    return "&H00FFFFFF&"


def format_ass_time(seconds: float) -> str:
    """Formats seconds into ASS timestamp format: H:MM:SS.cs (centiseconds)."""
    if seconds < 0:
        seconds = 0
    hrs = int(seconds // 3600)
    mins = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cs = int(round((seconds - int(seconds)) * 100))
    if cs >= 100:
        secs += 1
        cs -= 100
    return f"{hrs}:{mins:02d}:{secs:02d}.{cs:02d}"


@dataclass
class SubStylePreset:
    name: str
    font_name: str
    font_size: int
    primary_color: str        # Base text color (hex)
    highlight_color: str      # Active word color (hex)
    outline_color: str        # Border color (hex)
    outline_width: float
    shadow_color: str         # Shadow color (hex)
    shadow_depth: float
    blur: float               # Soft glow / blur
    all_caps: bool = True
    animation: str = "bounce" # "bounce", "pop", "fade", "none"
    anim_speed_ms: int = 100  # Snap duration in ms (50 - 250)
    anim_scale: int = 118     # Scale percentage (105 - 140)
    margin_v: int = 560       # Vertical distance from bottom (for 1080x1920)


PRESETS = {
    "hormozi": SubStylePreset(
        name="Hormozi",
        font_name="Montserrat ExtraBold",
        font_size=82,
        primary_color="#FFFFFF",
        highlight_color="#FFE600",  # Punchy bright yellow
        outline_color="#000000",
        outline_width=5.5,
        shadow_color="#000000",
        shadow_depth=3.0,
        blur=0.0,
        all_caps=True,
        animation="bounce",
        anim_speed_ms=100,
        anim_scale=118,
        margin_v=560,
    ),
    "mrbeast": SubStylePreset(
        name="MrBeast",
        font_name="Impact",
        font_size=88,
        primary_color="#FFE600",   # Yellow base
        highlight_color="#FFFFFF", # White highlight
        outline_color="#000000",
        outline_width=6.0,
        shadow_color="#000000",
        shadow_depth=3.5,
        blur=0.0,
        all_caps=True,
        animation="pop",
        anim_speed_ms=80,
        anim_scale=114,
        margin_v=560,
    ),
    "neon_glow": SubStylePreset(
        name="Neon Glow",
        font_name="Montserrat ExtraBold",
        font_size=80,
        primary_color="#FFFFFF",
        highlight_color="#00FFCC",  # Neon Cyan
        outline_color="#002b20",
        outline_width=4.0,
        shadow_color="#00FFCC",
        shadow_depth=0.0,
        blur=5.0,                   # Glow effect
        all_caps=True,
        animation="pop",
        anim_speed_ms=90,
        anim_scale=112,
        margin_v=560,
    ),
    "clean_minimal": SubStylePreset(
        name="Clean Minimal",
        font_name="Arial",
        font_size=74,
        primary_color="#FFFFFF",
        highlight_color="#FF3366",  # Modern accent pink/red
        outline_color="#101010",
        outline_width=3.5,
        shadow_color="#000000",
        shadow_depth=2.0,
        blur=0.0,
        all_caps=False,
        animation="fade",
        anim_speed_ms=80,
        anim_scale=100,
        margin_v=540,
    ),
    "tiktok_bold": SubStylePreset(
        name="TikTok Bold",
        font_name="The Bold Font",
        font_size=84,
        primary_color="#FFFFFF",
        highlight_color="#00FF66",  # Neon Green
        outline_color="#000000",
        outline_width=5.0,
        shadow_color="#000000",
        shadow_depth=2.5,
        blur=0.0,
        all_caps=True,
        animation="bounce",
        anim_speed_ms=100,
        anim_scale=118,
        margin_v=560,
    ),
    "cyberpunk": SubStylePreset(
        name="Cyberpunk",
        font_name="Impact",
        font_size=84,
        primary_color="#00FFFF",   # Cyan
        highlight_color="#FF007F", # Neon Hot Pink
        outline_color="#000000",
        outline_width=5.5,
        shadow_color="#FF007F",
        shadow_depth=0.0,
        blur=3.5,
        all_caps=True,
        animation="bounce",
        anim_speed_ms=90,
        anim_scale=120,
        margin_v=560,
    ),
    "fire_red": SubStylePreset(
        name="Fire Red",
        font_name="Montserrat ExtraBold",
        font_size=82,
        primary_color="#FFFFFF",
        highlight_color="#FF2200",  # Intense Fire Red
        outline_color="#000000",
        outline_width=5.5,
        shadow_color="#000000",
        shadow_depth=3.0,
        blur=0.0,
        all_caps=True,
        animation="pop",
        anim_speed_ms=85,
        anim_scale=115,
        margin_v=560,
    )
}


def build_ass_header(preset: SubStylePreset, play_res_x: int = 1080, play_res_y: int = 1920) -> str:
    """Generates the ASS script header and style definition for 9:16 video."""
    pri_col = hex_to_ass_color(preset.primary_color)
    sec_col = hex_to_ass_color(preset.highlight_color)
    out_col = hex_to_ass_color(preset.outline_color)
    sha_col = hex_to_ass_color(preset.shadow_color)

    # Alignment 2 = Bottom center
    alignment = 2

    header = f"""[Script Info]
Title: Submaxxing TikTok Subtitles
ScriptType: v4.00+
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {play_res_x}
PlayResY: {play_res_y}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{preset.font_name},{preset.font_size},{pri_col},{sec_col},{out_col},{sha_col},-1,0,0,0,100,100,0,0,1,{preset.outline_width},{preset.shadow_depth},{alignment},60,60,{preset.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    return header


@dataclass
class WordTiming:
    word: str
    start: float
    end: float


@dataclass
class SubChunk:
    words: List[WordTiming]
    start: float
    end: float


def generate_dialogue_line(chunk: SubChunk, active_idx: int, preset: SubStylePreset) -> str:
    """
    Renders an ASS Dialogue line where `active_idx` within `chunk.words` is highlighted.
    Fixes the fade bug by applying fade smoothly at chunk boundaries, not flickering per word.
    """
    active_word = chunk.words[active_idx]
    start_str = format_ass_time(active_word.start)
    end_str = format_ass_time(active_word.end)
    word_dur_ms = max(50, int((active_word.end - active_word.start) * 1000))

    pri_ass = hex_to_ass_color(preset.primary_color)
    high_ass = hex_to_ass_color(preset.highlight_color)

    # 1. Base tags for the line
    tags = [f"\\c{pri_ass}"]
    if preset.blur > 0:
        tags.append(f"\\blur{preset.blur:.1f}")

    # Fix Fade:
    # A multi-word chunk should fade in only on word 0, and fade out only on the last word.
    # It must NEVER fade in/out between words in the same phrase (which caused the strobe bug).
    if preset.animation == "fade":
        fade_dur = min(80, max(30, preset.anim_speed_ms))
        is_first = (active_idx == 0)
        is_last = (active_idx == len(chunk.words) - 1)

        if is_first and is_last:
            # Single word chunk: fade in and fade out
            safe_fade = min(fade_dur, word_dur_ms // 3)
            tags.append(f"\\fad({safe_fade},{safe_fade})")
        elif is_first:
            # First word of phrase: fade in only
            safe_fade = min(fade_dur, word_dur_ms // 2)
            tags.append(f"\\fad({safe_fade},0)")
        elif is_last:
            # Last word of phrase: fade out only
            safe_fade = min(fade_dur, word_dur_ms // 2)
            tags.append(f"\\fad(0,{safe_fade})")
        # Middle words: NO fade tag! Phrase stays solid.

    line_prefix = "{" + "".join(tags) + "}"

    # 2. Build words with active word highlighted and animated
    formatted_words = []
    scale = max(100, preset.anim_scale)
    speed = max(40, min(300, preset.anim_speed_ms))

    for i, w in enumerate(chunk.words):
        raw_text = w.word.upper() if preset.all_caps else w.word
        if i == active_idx:
            # Active word animation
            if preset.animation in ["bounce", "pop"]:
                anim = f"\\fscx{scale}\\fscy{scale}\\t(0,{speed},\\fscx100\\fscy100)"
            else:
                anim = ""
            formatted_words.append(f"{{\\c{high_ass}{anim}}}{raw_text}{{\\c{pri_ass}\\fscx100\\fscy100}}")
        else:
            formatted_words.append(raw_text)

    line_text = " ".join(formatted_words)
    full_text = f"{line_prefix}{line_text}"

    return f"Dialogue: 0,{start_str},{end_str},Default,,0,0,0,,{full_text}"


def chunks_to_ass(chunks: List[SubChunk], preset: SubStylePreset, play_res_x: int = 1080, play_res_y: int = 1920) -> str:
    """Converts a list of word chunks into a full ASS subtitle document."""
    lines = [build_ass_header(preset, play_res_x, play_res_y)]

    for chunk in chunks:
        if not chunk.words:
            continue
        for idx in range(len(chunk.words)):
            line = generate_dialogue_line(chunk, idx, preset)
            lines.append(line)

    return "\n".join(lines) + "\n"
