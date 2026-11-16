<div align="center">

# ⚡ SUBMAXXING STUDIO PRO

**The 100% Free, Local & GPU-Accelerated TikTok / Shorts Subtitle Generator**

*Say goodbye to Submagic, Captions.ai, and CapCut Pro paywalls forever.*

[![Python](https://img.shields.io/badge/Python-3.10%20%7C%203.11%20%7C%203.12-blue?logo=python&logoColor=white)](https://www.python.org/)
[![NVIDIA CUDA](https://img.shields.io/badge/GPU%20Acceleration-NVIDIA%20NVENC%20%2B%20CUDA-green?logo=nvidia&logoColor=white)](https://developer.nvidia.com/cuda-zone)
[![Whisper](https://img.shields.io/badge/Whisper-large--v3--turbo-orange)](https://github.com/SYSTRAN/faster-whisper)
[![License: MIT](https://img.shields.io/badge/License-MIT-purple.svg)](LICENSE)
[![Vibe Coded](https://img.shields.io/badge/Vibe%20Coded%20By-Gemini%203.8--Flash--High%20(Google%20DeepMind)-7928CA?style=flat&logo=google)](https://deepmind.google/)

[English](#-english) • [Français](#-français)

</div>

---

## 🌟 Highlights

- 🆓 **100% Free & Unlimited**: Runs locally on your machine. No cloud subscriptions, no usage quotas, no watermarks.
- ⚡ **RTX GPU-Accelerated**: Transcribe with **Whisper `large-v3-turbo`** on CUDA and burn subtitles with **NVIDIA NVENC** in 2–3 seconds per video.
- ✂️ **Smart Sentence Slicing**: Converts long paragraph `.srt` files into punchy, bite-sized 1-to-3-word TikTok chunks with precise timing interpolation.
- 🇫🇷 **French Clitics & Elisions Fix**: Intelligently binds `c'`, `d'`, `l'`, `j'`, `qu'` (e.g. `c'est`, `d'accord`, `l'autre`) so apostrophes are never split across screens in isolation.
- 📱 **Official TikTok 9:16 Safe Zone Mockup**: Real-time visual preview displaying official TikTok UI elements (likes, avatar, sound, description, bottom bar) with an optional Safe Zone guide.
- 🎨 **Neumorphic Dark UI**: Soft UI design with micro-animations, bilingual switcher (**EN / FR**), and Windows file explorer dialogs.
- 🎛️ **Advanced Customization**: Complete control over font families, sizes, highlight colors, outline thickness, drop shadows, glow blur, and bounce/pop animation speeds.
- 🎬 **CapCut / Premiere Overlay Export**: Export transparent **Apple ProRes 4444 (.MOV)** or **Alpha WebM** subtitle overlays to drop directly onto track 2 in your favorite video editor.

---

## 🚀 Quick Start (1-Click on Windows)

### 1. Installation
Clone the repository and run the automated installer:
```bash
git clone https://github.com/YOUR_USERNAME/submaxxing.git
cd submaxxing
```
Double-click on **`install.bat`** (or run `./install.bat` in terminal).  
*The installer automatically configures the Python virtual environment, installs CUDA/Whisper dependencies, and checks for FFmpeg.*

### 2. Launch
Double-click on **`start.bat`**!  
The Neumorphic Studio opens automatically in your browser at `http://127.0.0.1:5055`.

---

## 🎨 Style Presets

| Preset | Description | Entrance Animation |
| :--- | :--- | :--- |
| **Hormozi** | Punchy yellow highlight, bold white text, thick black outline | Dynamic Bounce Pop |
| **MrBeast** | Classic yellow/white Impact font, bold drop shadow | Snap Pop |
| **Neon Glow** | Cyan / Teal electric glow with soft Gaussian blur halo | Neon Pop |
| **TikTok Bold** | *The Bold Font* with neon green highlight | Dynamic Bounce |
| **Cyberpunk** | High-contrast Cyan base with Hot Pink active highlight | Cyber Bounce |
| **Fire Red** | Intense fiery red active highlight on clean white text | Punchy Pop |
| **Clean Minimal**| Sleek modern typography with seamless chunk fade | Smooth Fade |

---

## 💻 Command Line Interface (CLI)

You can also use Submaxxing directly from terminal or in automated video pipelines:

```bash
# 1. Use existing SRT (e.g. from Buzz Whisper) with Hormozi preset (2 words/screen):
python submaxxing.py "input_video.mp4" --srt "subtitles.srt" --style hormozi -w 2

# 2. Auto-transcribe video directly with Whisper large-v3-turbo (FR or EN) on RTX GPU:
python submaxxing.py "input_video.mp4" --transcribe --lang fr --style hormozi

# 3. Custom advanced styling (neon green highlight, 6px outline, 125% pop scale):
python submaxxing.py "input_video.mp4" --srt "subtitles.srt" --highlight-color "#00FF66" --outline-width 6.0 --anim-scale 125 --anim-speed 80

# 4. Export transparent ProRes 4444 (.MOV) overlay for CapCut / Premiere:
python submaxxing.py "input_video.mp4" --srt "subtitles.srt" --overlay-only
```

---

## 🇫🇷 Français

Outil gratuit, local et open-source conçu pour les **clippers TikTok, Shorts et Reels** qui en ont marre de payer des abonnements mensuels.

### Fonctionnalités Clés :
- **Découpage intelligent** : Transforme les phrases longues de vos fichiers `.srt` en blocs de 1 à 3 mots ultra-digestes.
- **Gestion des élisions françaises** : Rapproche automatiquement les `c'`, `d'`, `l'`, `j'`, `qu'` (ex: `c'est`, `d'accord`) pour ne jamais avoir un `C'` coupé tout seul à l'écran.
- **Accélération GPU RTX** : Transcription Whisper `large-v3-turbo` et rendu vidéo NVENC en 2-3 secondes.
- **Aperçu Safe Zone TikTok** : Visualisez vos sous-titres directement sur la vraie interface TikTok pour éviter toute superposition avec les boutons ou la description.
- **Export Overlay Transparent** : Exportez des fichiers **Apple ProRes 4444 (.MOV)** transparents à déposer directement dans **CapCut** ou **Premiere Pro**.

**Pour lancer l'application :**  
1. Double-cliquez sur `install.bat` la première fois.
2. Double-cliquez sur `start.bat`.

---

## 🛠️ Credits & Attribution

This project was proudly **vibe-coded by Gemini 3.8-Flash-High** (Google DeepMind).

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
