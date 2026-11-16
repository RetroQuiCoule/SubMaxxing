# ⚡ SUBMAXXING

> **100% Free & Local TikTok / Shorts Subtitle Generator.**  
> GPU-accelerated animated captions without paywalls, subscriptions, or watermarks.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue?logo=python&logoColor=white)](https://www.python.org/)
[![GPU](https://img.shields.io/badge/GPU-NVENC%20%2B%20CUDA-green?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Whisper](https://img.shields.io/badge/Whisper-large--v3--turbo-orange)](https://github.com/SYSTRAN/faster-whisper)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)
[![Vibe Coded](https://img.shields.io/badge/Vibe%20Coded%20By-Gemini%203.8--Flash--High-7928CA?logo=google)](https://deepmind.google/)

---

## ⚡ Features

- **Auto-Reframe (16:9 → 9:16)**: Face-tracking Smart Pan, split-screen podcasts, blurred background, plus live sharpness/contrast/vignette grading.
- **Smart SRT Slicing**: Converts long sentence `.srt` files into dynamic 1-to-3-word TikTok chunks.
- **French Elisions Handled**: Binds `c'`, `d'`, `l'`, `j'`, `qu'` (e.g. `c'est`, `d'accord`) so apostrophes are never split.
- **Local Whisper (`large-v3-turbo`)**: Fast local transcription with CUDA acceleration or automatic CPU fallback.
- **Neumorphic Studio (EN / FR)**: Bilingual web UI with file pickers and real-time TikTok 9:16 Safe Zone preview.
- **Animations & Glow**: Bounce, pop, fade, karaoke word-highlight, outline, and neon glow.
- **CapCut / Premiere Overlay**: Export transparent **ProRes 4444 (.mov)** or burned MP4.

---

## 🚀 Quick Start (Windows)

1. **Install** (first time only):
   ```bash
   git clone https://github.com/RetroQuiCoule/SubMaxxing.git
   cd SubMaxxing
   ```
   Run `install.bat`

2. **Launch**:
   Run `start.bat` (opens `http://127.0.0.1:5055`)

---

## 🎨 Presets

| Preset | Style | Animation |
| :--- | :--- | :--- |
| **Hormozi** | Yellow highlight, bold white text, black border | Bounce Pop |
| **MrBeast** | Yellow base, white highlight, Impact font | Snap Pop |
| **Neon Glow** | Cyan / Teal electric glow with blur halo | Neon Pop |
| **TikTok Bold** | *The Bold Font* with neon green highlight | Bounce |
| **Cyberpunk** | Cyan base with hot pink active highlight | Cyber Bounce |
| **Fire Red** | Intense fiery red active highlight | Punchy Pop |
| **Clean Minimal** | Clean font, smooth seamless fade | Smooth Fade |

---

## 💻 CLI Usage

```bash
# Slices an existing SRT into 2 words/chunk with Hormozi preset
python submaxxing.py "video.mp4" --srt "subs.srt" --style hormozi -w 2

# Direct transcription with Whisper large-v3-turbo (FR)
python submaxxing.py "video.mp4" --transcribe --lang fr --style hormozi

# Export transparent ProRes 4444 overlay for CapCut
python submaxxing.py "video.mp4" --srt "subs.srt" --overlay-only
```

---

## 🛠️ Credits & License

- **Vibe-coded by Gemini 3.8-Flash-High** (Google DeepMind).
- Licensed under the [MIT License](LICENSE).
