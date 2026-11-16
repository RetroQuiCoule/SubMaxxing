"""
Submaxxing Web Studio - Neumorphic Pro Edition with Reframe Studio.
Full bilingual support (English default / French toggle),
Clean file selector buttons (no ugly text boxes),
Dedicated 16:9 -> 9:16 Reframe Studio with Face Tracking & Video Grading,
Official TikTok 9:16 UI Safe Zone, advanced customization, and GPU acceleration.
"""

import os
import sys

# Suppress HuggingFace symlinks warning and patch PyAV metadata_errors
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"
try:
    import av
    _orig_av_open = av.open
    def _safe_av_open(*args, **kwargs):
        kwargs.pop("metadata_errors", None)
        return _orig_av_open(*args, **kwargs)
    av.open = _safe_av_open
except Exception:
    pass

import json
import re
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
import urllib.parse
from styles import PRESETS, SubStylePreset, chunks_to_ass
from chunker import srt_to_chunks
from renderer import (
    render_subtitles_to_video,
    render_transparent_overlay,
    get_video_info,
)
from reframe import process_reframe

PORT = 5055
PREVIEW_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web_preview.mp4")
REFRAME_PREVIEW_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "reframe_preview.mp4")

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Submaxxing Studio Pro - TikTok Subtitles & Reframe</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #0d111a;
            --surface: #141a26;
            --surface-raised: #182030;
            --border: rgba(255, 255, 255, 0.05);
            --border-highlight: rgba(255, 255, 255, 0.1);
            --accent: #00f2fe;
            --accent-glow: rgba(0, 242, 254, 0.35);
            --accent-grad: linear-gradient(135deg, #00f2fe 0%, #4facfe 100%);
            --reframe-accent: #a855f7;
            --reframe-grad: linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
            --pink: #ff007f;
            --yellow: #ffe600;
            --text: #f8fafc;
            --text-dim: #94a3b8;
            --text-muted: #64748b;
            --neu-shadow: 6px 6px 16px rgba(0, 0, 0, 0.5), -4px -4px 12px rgba(255, 255, 255, 0.02);
            --neu-inset: inset 3px 3px 6px rgba(0, 0, 0, 0.5), inset -2px -2px 5px rgba(255, 255, 255, 0.02);
        }

        /* Dynamic Reframe Purple Theme */
        body.theme-reframe {
            --bg: #0b0714;
            --surface: #140d24;
            --surface-raised: #1e1336;
            --border: rgba(168, 85, 247, 0.16);
            --border-highlight: rgba(168, 85, 247, 0.38);
            --accent: #c084fc;
            --accent-glow: rgba(192, 132, 252, 0.45);
            --accent-grad: linear-gradient(135deg, #a855f7 0%, #ec4899 100%);
            --neu-shadow: 6px 6px 18px rgba(0, 0, 0, 0.6), -4px -4px 12px rgba(168, 85, 247, 0.04);
            --neu-inset: inset 3px 3px 6px rgba(0, 0, 0, 0.6), inset -2px -2px 5px rgba(168, 85, 247, 0.04);
        }
        body.theme-reframe .navbar {
            border-color: rgba(168, 85, 247, 0.25);
            box-shadow: 0 8px 24px rgba(0, 0, 0, 0.5), 0 0 15px rgba(168, 85, 247, 0.12);
        }
        body.theme-reframe .brand-title {
            background: linear-gradient(90deg, #ffffff 40%, #c084fc 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        body.theme-reframe .brand-badge {
            background: rgba(168, 85, 247, 0.18);
            color: #d8b4fe;
            border-color: rgba(168, 85, 247, 0.45);
        }
        body.theme-reframe .phone-wrapper {
            border-color: rgba(168, 85, 247, 0.4);
            box-shadow: 0 20px 50px rgba(0, 0, 0, 0.8), 0 0 25px rgba(168, 85, 247, 0.2);
        }
        body.theme-reframe .btn-pill:hover {
            border-color: #a855f7;
            color: #d8b4fe;
        }
        body, .navbar, .card, .phone-wrapper {
            transition: background 0.3s ease, border-color 0.3s ease, box-shadow 0.3s ease;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg);
            color: var(--text);
            min-height: 100vh;
            padding: 16px 24px 36px 24px;
        }

        /* Top Navbar */
        .navbar {
            max-width: 1260px;
            margin: 0 auto 20px auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 20px;
            background: var(--surface);
            border-radius: 16px;
            border: 1px solid var(--border);
            box-shadow: var(--neu-shadow);
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
            text-decoration: none;
        }
        .brand-logo {
            width: 36px;
            height: 36px;
            background: var(--accent-grad);
            border-radius: 10px;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: 0 4px 14px var(--accent-glow);
        }
        .brand-title {
            font-size: 1.25rem;
            font-weight: 900;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #ffffff 40%, var(--accent) 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
        .brand-badge {
            font-size: 0.65rem;
            font-weight: 700;
            background: rgba(0, 242, 254, 0.12);
            color: var(--accent);
            border: 1px solid rgba(0, 242, 254, 0.3);
            padding: 2px 7px;
            border-radius: 6px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }

        .nav-right {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .lang-switch {
            display: flex;
            align-items: center;
            background: #090d15;
            padding: 4px;
            border-radius: 10px;
            box-shadow: var(--neu-inset);
            border: 1px solid var(--border);
        }
        .lang-btn {
            background: none;
            border: none;
            color: var(--text-muted);
            padding: 5px 12px;
            font-size: 0.8rem;
            font-weight: 700;
            border-radius: 7px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .lang-btn.active {
            background: var(--surface-raised);
            color: var(--text);
            box-shadow: 0 2px 6px rgba(0,0,0,0.4);
        }

        /* Layouts */
        .main-layout {
            display: grid;
            grid-template-columns: 1.15fr 0.85fr;
            gap: 24px;
            max-width: 1260px;
            margin: 0 auto;
            align-items: start;
        }
        @media (max-width: 980px) {
            .main-layout { grid-template-columns: 1fr; }
        }

        /* Views */
        .view-section { display: none; }
        .view-section.active { display: block; }

        /* Neumorphic Cards */
        .card {
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 18px;
            box-shadow: var(--neu-shadow);
            transition: border-color 0.2s;
        }
        .card:hover { border-color: var(--border-highlight); }
        .card-title {
            font-size: 1.05rem;
            font-weight: 700;
            margin-bottom: 14px;
            color: #fff;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .card-title-left {
            display: flex;
            align-items: center;
            gap: 10px;
        }

        .form-group { margin-bottom: 14px; }
        label {
            display: block;
            font-size: 0.82rem;
            font-weight: 600;
            margin-bottom: 6px;
            color: var(--text-dim);
        }

        /* Button-Only File Controls */
        .file-control-row {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
        }
        .btn-pill {
            background: var(--surface-raised);
            border: 1px solid var(--border-highlight);
            color: var(--text);
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 0.88rem;
            font-weight: 700;
            cursor: pointer;
            white-space: nowrap;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: 3px 3px 8px rgba(0,0,0,0.4), -2px -2px 6px rgba(255,255,255,0.02);
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .btn-pill:hover {
            transform: translateY(-1px);
            border-color: var(--accent);
            color: var(--accent);
        }
        .btn-pill:active {
            transform: translateY(1px);
            box-shadow: var(--neu-inset);
        }

        .btn-reframe-trigger {
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.15) 0%, rgba(236, 72, 153, 0.15) 100%);
            border: 1px solid rgba(168, 85, 247, 0.4);
            color: #d8b4fe;
            border-radius: 10px;
            padding: 10px 18px;
            font-size: 0.88rem;
            font-weight: 700;
            cursor: pointer;
            display: inline-flex;
            align-items: center;
            gap: 8px;
            box-shadow: 3px 3px 8px rgba(0,0,0,0.4);
            transition: all 0.2s;
        }
        .btn-reframe-trigger:hover {
            transform: translateY(-1px);
            background: linear-gradient(135deg, rgba(168, 85, 247, 0.25) 0%, rgba(236, 72, 153, 0.25) 100%);
            border-color: #c084fc;
            color: #fff;
            box-shadow: 0 4px 14px rgba(168, 85, 247, 0.3);
        }

        .file-badge {
            background: #090d15;
            border: 1px solid var(--border);
            padding: 8px 14px;
            border-radius: 8px;
            font-size: 0.82rem;
            color: var(--text-dim);
            font-family: Consolas, monospace;
            box-shadow: var(--neu-inset);
            flex: 1;
            min-width: 160px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }
        .file-badge.has-file {
            color: var(--accent);
            border-color: rgba(0, 242, 254, 0.3);
        }

        /* Inputs & Sliders */
        select {
            width: 100%;
            padding: 10px 14px;
            background: #090d15;
            border: 1px solid var(--border);
            border-radius: 10px;
            color: #fff;
            font-size: 0.88rem;
            font-family: inherit;
            box-shadow: var(--neu-inset);
            transition: all 0.2s;
        }
        select:focus {
            outline: none;
            border-color: var(--accent);
        }

        .row {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 14px;
        }

        .slider-group {
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .slider-group input[type="range"] {
            flex: 1;
            accent-color: var(--accent);
            cursor: pointer;
            height: 6px;
            border-radius: 4px;
            background: #090d15;
        }
        .slider-val {
            font-family: Consolas, monospace;
            font-size: 0.82rem;
            color: var(--accent);
            width: 48px;
            text-align: right;
            font-weight: 700;
        }

        .color-picker-box {
            display: flex;
            align-items: center;
            gap: 8px;
            background: #090d15;
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 6px 12px;
            box-shadow: var(--neu-inset);
        }
        .color-picker-box input[type="color"] {
            border: none;
            width: 30px;
            height: 30px;
            border-radius: 6px;
            background: none;
            cursor: pointer;
        }
        .color-picker-box input[type="text"] {
            border: none;
            background: none;
            box-shadow: none;
            padding: 0;
            font-family: Consolas, monospace;
            font-size: 0.85rem;
            font-weight: 600;
            width: 80px;
            color: #fff;
        }

        .toggle-container {
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 14px;
            background: #090d15;
            border-radius: 10px;
            border: 1px solid var(--border);
            box-shadow: var(--neu-inset);
            cursor: pointer;
            font-size: 0.86rem;
        }
        .toggle-container input {
            cursor: pointer;
            width: 17px;
            height: 17px;
            accent-color: var(--accent);
        }

        /* Advanced Accordion */
        .advanced-header {
            cursor: pointer;
            user-select: none;
            background: var(--surface-raised);
            border: 1px solid var(--border-highlight);
            padding: 12px 18px;
            border-radius: 12px;
            margin-bottom: 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            font-weight: 700;
            font-size: 0.92rem;
            color: var(--accent);
            box-shadow: var(--neu-shadow);
            transition: all 0.2s;
        }
        .advanced-header:hover {
            border-color: var(--accent);
            transform: translateY(-1px);
        }
        .advanced-content {
            display: none;
            padding-top: 12px;
            border-top: 1px dashed var(--border);
            margin-top: 12px;
        }

        /* 9:16 Phone Mockup */
        .preview-sticky {
            position: sticky;
            top: 20px;
        }
        .phone-wrapper {
            width: 330px;
            height: 586px;
            margin: 0 auto 16px auto;
            background: #000;
            border: 4px solid #232c3d;
            border-radius: 36px;
            position: relative;
            overflow: hidden;
            box-shadow: 0 20px 50px rgba(0,0,0,0.7), var(--neu-shadow);
            user-select: none;
        }
        .phone-video-bg {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            object-fit: cover;
            display: none;
            z-index: 1;
        }

        /* Reframe Phone Preview Elements */
        .reframe-phone-video {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            object-fit: cover;
            display: none;
            z-index: 1;
            background: #000;
        }
        .reframe-vignette-overlay {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            pointer-events: none;
            z-index: 2;
            transition: box-shadow 0.2s ease;
        }
        .reframe-mode-badge {
            position: absolute;
            top: 14px; right: 14px;
            background: rgba(15, 10, 25, 0.85);
            backdrop-filter: blur(8px);
            -webkit-backdrop-filter: blur(8px);
            color: #e9d5ff;
            border: 1px solid rgba(168, 85, 247, 0.4);
            font-size: 0.72rem;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 20px;
            z-index: 4;
            pointer-events: none;
            box-shadow: 0 4px 12px rgba(0,0,0,0.5);
        }
        .reframe-placeholder {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 28px;
            text-align: center;
            z-index: 3;
            background: radial-gradient(circle at center, rgba(168, 85, 247, 0.12) 0%, rgba(13, 8, 22, 0.96) 80%);
        }
        .reframe-ph-icon {
            font-size: 3.2rem;
            margin-bottom: 14px;
            filter: drop-shadow(0 4px 14px rgba(168, 85, 247, 0.5));
            animation: pulsePhIcon 3s ease-in-out infinite;
        }
        @keyframes pulsePhIcon {
            0%, 100% { transform: scale(1); opacity: 0.9; }
            50% { transform: scale(1.08); opacity: 1; }
        }
        .reframe-ph-title {
            font-size: 1.1rem;
            font-weight: 800;
            color: #f5f3ff;
            margin-bottom: 8px;
        }
        .reframe-ph-desc {
            font-size: 0.82rem;
            line-height: 1.45;
            color: #a78bfa;
        }

        /* TikTok UI Overlay */
        .tiktok-overlay {
            position: absolute;
            top: 0; left: 0;
            width: 100%; height: 100%;
            z-index: 5;
            pointer-events: none;
            display: flex;
            flex-direction: column;
            justify-content: space-between;
            padding: 14px 12px 6px 12px;
            box-sizing: border-box;
            color: #fff;
            text-shadow: 0 1px 3px rgba(0,0,0,0.85);
        }
        .tt-top {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 0 6px;
            font-size: 0.88rem;
            font-weight: 600;
        }
        .tt-tabs {
            display: flex;
            gap: 16px;
            margin: 0 auto;
        }
        .tt-tab-foryou {
            position: relative;
            font-weight: 700;
        }
        .tt-tab-foryou::after {
            content: '';
            position: absolute;
            bottom: -4px; left: 50%;
            transform: translateX(-50%);
            width: 24px; height: 2px;
            background: #fff;
            border-radius: 2px;
        }
        .tt-tab-following {
            color: rgba(255,255,255,0.7);
            position: relative;
        }
        .tt-tab-following::after {
            content: '';
            position: absolute;
            top: 0px; right: -7px;
            width: 6px; height: 6px;
            background: #ff004f;
            border-radius: 50%;
        }

        .tt-right {
            position: absolute;
            right: 10px;
            bottom: 78px;
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 14px;
            font-size: 0.68rem;
            font-weight: 600;
        }
        .tt-action {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }
        .tt-avatar {
            width: 38px; height: 38px;
            border-radius: 50%;
            background: #777;
            border: 1.5px solid #fff;
            position: relative;
            margin-bottom: 6px;
        }
        .tt-avatar-plus {
            position: absolute;
            bottom: -5px; left: 50%;
            transform: translateX(-50%);
            background: #ff004f;
            color: #fff;
            border-radius: 50%;
            width: 16px; height: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 0.75rem;
            font-weight: 900;
        }
        .tt-icon {
            font-size: 1.5rem;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.6));
        }
        .tt-disc {
            width: 32px; height: 32px;
            border-radius: 50%;
            background: radial-gradient(circle, #222 30%, #555 40%, #111 70%);
            border: 6px solid #222;
            animation: spin 3s linear infinite;
            margin-top: 4px;
        }
        @keyframes spin { 100% { transform: rotate(360deg); } }

        .tt-bottom-left {
            position: absolute;
            left: 12px;
            bottom: 54px;
            max-width: 215px;
            font-size: 0.76rem;
            line-height: 1.35;
        }
        .tt-user { font-weight: 700; font-size: 0.88rem; margin-bottom: 2px; }
        .tt-desc { color: rgba(255,255,255,0.92); }
        .tt-music {
            display: flex;
            align-items: center;
            gap: 6px;
            margin-top: 4px;
            font-size: 0.72rem;
            color: rgba(255,255,255,0.85);
        }

        .tt-bottom-bar {
            position: absolute;
            bottom: 0; left: 0;
            width: 100%;
            height: 44px;
            background: rgba(0,0,0,0.92);
            border-top: 1px solid rgba(255,255,255,0.12);
            display: flex;
            justify-content: space-around;
            align-items: center;
            font-size: 0.62rem;
            font-weight: 600;
            color: rgba(255,255,255,0.65);
        }
        .tt-nav-item {
            display: flex;
            flex-direction: column;
            align-items: center;
            gap: 2px;
        }
        .tt-nav-active { color: #fff; }
        .tt-add-btn {
            width: 38px; height: 26px;
            background: #fff;
            border-radius: 7px;
            position: relative;
            display: flex;
            align-items: center;
            justify-content: center;
            color: #000;
            font-size: 1.1rem;
            font-weight: 900;
            box-shadow: -2.5px 0 0 #00f2fe, 2.5px 0 0 #ff004f;
        }

        .mockup-sub-container {
            position: absolute;
            width: 90%;
            left: 5%;
            text-align: center;
            z-index: 10;
            pointer-events: none;
            transition: bottom 0.15s ease-out;
            bottom: 170px;
        }
        .mockup-sub-text {
            display: inline-block;
            line-height: 1.25;
            word-wrap: break-word;
            transition: transform 0.08s ease-out, opacity 0.15s ease-out;
        }

        .safe-zone-guide {
            position: absolute;
            top: 48px; left: 10px; right: 54px; bottom: 120px;
            border: 1px dashed rgba(0, 242, 254, 0.45);
            border-radius: 12px;
            pointer-events: none;
            z-index: 4;
            display: none;
        }
        .safe-zone-label {
            position: absolute;
            top: 6px; left: 6px;
            font-size: 0.65rem;
            color: var(--accent);
            background: rgba(0,0,0,0.6);
            padding: 2px 6px;
            border-radius: 4px;
        }

        /* Buttons */
        .btn-preview {
            width: 100%;
            padding: 12px;
            background: var(--surface-raised);
            border: 1px solid var(--accent);
            color: var(--accent);
            border-radius: 12px;
            font-size: 0.92rem;
            font-weight: 700;
            cursor: pointer;
            margin-bottom: 10px;
            box-shadow: 0 4px 14px rgba(0, 242, 254, 0.12);
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
        }
        .btn-preview:hover {
            background: rgba(0, 242, 254, 0.12);
            transform: translateY(-1px);
        }

        .btn-submit {
            width: 100%;
            padding: 15px;
            background: var(--accent-grad);
            border: none;
            border-radius: 12px;
            color: #080d17;
            font-size: 1.05rem;
            font-weight: 800;
            cursor: pointer;
            box-shadow: 0 6px 20px var(--accent-glow);
            transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
        }
        .btn-submit:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 242, 254, 0.45);
        }

        .btn-reframe-submit {
            background: var(--reframe-grad);
            box-shadow: 0 6px 20px rgba(168, 85, 247, 0.4);
            color: #fff;
        }

        #statusBox {
            display: none;
            margin-top: 16px;
            padding: 14px;
            border-radius: 10px;
            background: #090d15;
            border: 1px solid var(--border);
            box-shadow: var(--neu-inset);
            font-family: Consolas, monospace;
            font-size: 0.85rem;
            white-space: pre-wrap;
            max-height: 220px;
            overflow-y: auto;
        }
    </style>
</head>
<body>
    <!-- Top Navbar -->
    <nav class="navbar">
        <a href="#" class="brand" onclick="switchView('subtitles')">
            <div class="brand-logo">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#080d17" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                    <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"></polygon>
                </svg>
            </div>
            <div>
                <span class="brand-title">SUBMAXXING</span>
                <span class="brand-badge" id="brandBadge">STUDIO PRO</span>
            </div>
        </a>

        <div class="nav-right">
            <button type="button" class="btn-pill" id="navBackBtn" style="display:none;" onclick="switchView('subtitles')">
                ⬅️ <span data-i18n="backToSubs">Back to Subtitles</span>
            </button>
            <div class="lang-switch">
                <button type="button" class="lang-btn active" id="btnLangEN" onclick="setLanguage('en')">EN</button>
                <button type="button" class="lang-btn" id="btnLangFR" onclick="setLanguage('fr')">FR</button>
            </div>
        </div>
    </nav>

    <!-- ================= VIEW 1: SUBTITLES STUDIO ================= -->
    <div id="viewSubtitles" class="view-section active">
        <div class="main-layout">
            <div class="controls-col">
                <form id="subForm">
                    <!-- 1. Files -->
                    <div class="card">
                        <div class="card-title">
                            <div class="card-title-left" data-i18n="section1Title">📁 1. Video & Subtitles</div>
                        </div>

                        <!-- Video Selection + Reframe button side-by-side -->
                        <div class="form-group">
                            <label data-i18n="videoLabel">9:16 Video (MP4 / MOV):</label>
                            <input type="hidden" id="videoPath" value="">
                            <div class="file-control-row">
                                <button type="button" class="btn-pill" onclick="browseFile('video')">
                                    📁 <span data-i18n="browseVideo">Browse Video...</span>
                                </button>
                                <button type="button" class="btn-reframe-trigger" onclick="openReframeView()">
                                    📐 <span data-i18n="reframeBtn">Reframe</span>
                                </button>
                                <div class="file-badge" id="videoBadge" data-i18n="noVideoSelected">No video selected</div>
                            </div>
                        </div>

                        <div class="form-group" style="margin-top:16px;">
                            <label class="toggle-container">
                                <input type="checkbox" id="autoTranscribe">
                                <span data-i18n="transcribeCheckbox">🎙️ <b>Transcribe with Local Whisper</b> (large-v3-turbo on RTX GPU)</span>
                            </label>
                        </div>

                        <!-- SRT Selection -->
                        <div class="form-group" id="srtGroup">
                            <label data-i18n="srtLabel">Existing SRT Subtitles (e.g. Buzz Whisper):</label>
                            <input type="hidden" id="srtPath" value="">
                            <div class="file-control-row">
                                <button type="button" class="btn-pill" onclick="browseFile('srt')">
                                    📁 <span data-i18n="browseSrt">Browse SRT...</span>
                                </button>
                                <div class="file-badge" id="srtBadge" data-i18n="noSrtSelected">No SRT selected</div>
                            </div>
                        </div>

                        <div class="row" id="whisperGroup" style="display: none;">
                            <div class="form-group">
                                <label data-i18n="langLabel">Audio Language:</label>
                                <select id="lang">
                                    <option value="fr">French (FR)</option>
                                    <option value="en">English (EN)</option>
                                    <option value="auto">Auto-detect</option>
                                </select>
                            </div>
                            <div class="form-group">
                                <label data-i18n="modelLabel">Whisper Model:</label>
                                <select id="model">
                                    <option value="large-v3-turbo" selected>large-v3-turbo (Ultra fast)</option>
                                    <option value="large-v3">large-v3 (Accuracy)</option>
                                    <option value="medium">medium</option>
                                </select>
                            </div>
                        </div>
                    </div>

                    <!-- 2. Style & Presets -->
                    <div class="card">
                        <div class="card-title">
                            <div class="card-title-left" data-i18n="section2Title">🎨 2. Style Preset & Pacing</div>
                        </div>

                        <div class="row">
                            <div class="form-group">
                                <label data-i18n="presetLabel">Style Preset:</label>
                                <select id="stylePreset" onchange="applyPresetToControls()">
                                    <option value="hormozi" selected>Hormozi (Yellow, black outline, bounce)</option>
                                    <option value="mrbeast">MrBeast (Yellow/White Impact, punchy)</option>
                                    <option value="neon_glow">Neon Glow (Cyan / Neon halo blur)</option>
                                    <option value="tiktok_bold">TikTok Bold (The Bold Font, Neon Green)</option>
                                    <option value="cyberpunk">Cyberpunk (Cyan & Hot Pink)</option>
                                    <option value="fire_red">Fire Red (Fiery intense red)</option>
                                    <option value="clean_minimal">Clean Minimal (Clean font, smooth fade)</option>
                                </select>
                            </div>

                            <div class="form-group">
                                <label data-i18n="wordsPerChunkLabel">Words Per Screen:</label>
                                <select id="wordsPerChunk" onchange="updateMockup()">
                                    <option value="1">1 word (Ultra punchy)</option>
                                    <option value="2" selected>2 words (Ideal short-form)</option>
                                    <option value="3">3 words (Short phrase)</option>
                                    <option value="4">4 words (Relaxed reading)</option>
                                </select>
                            </div>
                        </div>

                        <div class="row">
                            <div class="form-group">
                                <label data-i18n="animationLabel">Animation:</label>
                                <select id="animation" onchange="updateMockup()">
                                    <option value="bounce" selected>Dynamic Bounce (Pop snap)</option>
                                    <option value="pop">Subtle Zoom Pop</option>
                                    <option value="fade">Smooth Fade (Seamless)</option>
                                    <option value="none">Static (No motion)</option>
                                </select>
                            </div>

                            <div class="form-group">
                                <label data-i18n="verticalPosLabel">Vertical Position (Height):</label>
                                <div class="slider-group">
                                    <input type="range" id="posY" min="350" max="850" value="560" oninput="updateMockup()">
                                    <span class="slider-val" id="posYVal">560px</span>
                                </div>
                            </div>
                        </div>

                        <!-- 3. Advanced Accordion -->
                        <div class="advanced-header" onclick="toggleAdvanced()">
                            <span data-i18n="advancedTitle">⚙️ ADVANCED MODE (Full Customization)</span>
                            <span id="advChevron">▼</span>
                        </div>

                        <div class="advanced-content" id="advancedContent">
                            <div class="row">
                                <div class="form-group">
                                    <label data-i18n="highlightColorLabel">Active Word (Highlight):</label>
                                    <div class="color-picker-box">
                                        <input type="color" id="highlightColor" value="#FFE600" oninput="syncColor('highlight')">
                                        <input type="text" id="highlightColorHex" value="#FFE600" onchange="syncColorHex('highlight')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label data-i18n="primaryColorLabel">Base Text Color:</label>
                                    <div class="color-picker-box">
                                        <input type="color" id="primaryColor" value="#FFFFFF" oninput="syncColor('primary')">
                                        <input type="text" id="primaryColorHex" value="#FFFFFF" onchange="syncColorHex('primary')">
                                    </div>
                                </div>
                            </div>

                            <div class="row">
                                <div class="form-group">
                                    <label data-i18n="outlineColorLabel">Outline Color:</label>
                                    <div class="color-picker-box">
                                        <input type="color" id="outlineColor" value="#000000" oninput="syncColor('outline')">
                                        <input type="text" id="outlineColorHex" value="#000000" onchange="syncColorHex('outline')">
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label data-i18n="outlineWidthLabel">Outline Thickness:</label>
                                    <div class="slider-group">
                                        <input type="range" id="outlineWidth" min="0" max="10" step="0.5" value="5.5" oninput="updateMockup()">
                                        <span class="slider-val" id="outlineWidthVal">5.5px</span>
                                    </div>
                                </div>
                            </div>

                            <div class="row">
                                <div class="form-group">
                                    <label data-i18n="shadowDepthLabel">Shadow Depth:</label>
                                    <div class="slider-group">
                                        <input type="range" id="shadowDepth" min="0" max="8" step="0.5" value="3.0" oninput="updateMockup()">
                                        <span class="slider-val" id="shadowDepthVal">3.0px</span>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label data-i18n="glowLabel">Glow / Neon Blur:</label>
                                    <div class="slider-group">
                                        <input type="range" id="glow" min="0" max="10" step="0.5" value="0.0" oninput="updateMockup()">
                                        <span class="slider-val" id="glowVal">0.0</span>
                                    </div>
                                </div>
                            </div>

                            <div class="row">
                                <div class="form-group">
                                    <label data-i18n="fontFamilyLabel">Font Family:</label>
                                    <select id="fontName" onchange="updateMockup()">
                                        <option value="Montserrat ExtraBold" selected>Montserrat ExtraBold (TikTok pro)</option>
                                        <option value="Impact">Impact (MrBeast classic)</option>
                                        <option value="The Bold Font">The Bold Font</option>
                                        <option value="Arial Black">Arial Black</option>
                                        <option value="Poppins SemiBold">Poppins</option>
                                        <option value="Arial">Arial Clean</option>
                                    </select>
                                </div>
                                <div class="form-group">
                                    <label data-i18n="fontSizeLabel">Font Size:</label>
                                    <div class="slider-group">
                                        <input type="range" id="fontSize" min="50" max="115" value="82" oninput="updateMockup()">
                                        <span class="slider-val" id="fontSizeVal">82px</span>
                                    </div>
                                </div>
                            </div>

                            <div class="row">
                                <div class="form-group">
                                    <label data-i18n="animSpeedLabel">Bounce / Pop Speed (ms):</label>
                                    <div class="slider-group">
                                        <input type="range" id="animSpeed" min="40" max="250" step="10" value="100" oninput="updateMockup()">
                                        <span class="slider-val" id="animSpeedVal">100ms</span>
                                    </div>
                                </div>
                                <div class="form-group">
                                    <label data-i18n="animScaleLabel">Peak Pop Scale (%):</label>
                                    <div class="slider-group">
                                        <input type="range" id="animScale" min="105" max="140" step="1" value="118" oninput="updateMockup()">
                                        <span class="slider-val" id="animScaleVal">118%</span>
                                    </div>
                                </div>
                            </div>

                            <div class="form-group" style="margin-top: 6px;">
                                <label class="toggle-container">
                                    <input type="checkbox" id="allCaps" checked onchange="updateMockup()">
                                    <span data-i18n="allCapsLabel"><b>Force ALL CAPS (Uppercase)</b></span>
                                </label>
                            </div>
                        </div>
                    </div>

                    <!-- 4. Export -->
                    <div class="card">
                        <div class="card-title">
                            <div class="card-title-left" data-i18n="section3Title">🚀 3. Render & Export</div>
                        </div>

                        <div class="form-group">
                            <label data-i18n="renderFormatLabel">Export Format:</label>
                            <select id="renderType">
                                <option value="burn" selected data-i18n="optBurn">🎬 Burned Video (Full MP4 with embedded subtitles via RTX GPU)</option>
                                <option value="overlay_mov" data-i18n="optProres">✨ Transparent ProRes 4444 Overlay (.MOV for CapCut / Premiere)</option>
                                <option value="overlay_webm" data-i18n="optWebm">🌐 Transparent WebM Overlay (.webm)</option>
                                <option value="both" data-i18n="optBoth">⚡ Both (Burned MP4 + Transparent ProRes)</option>
                            </select>
                        </div>

                        <button type="submit" class="btn-submit" id="btnSubmit" data-i18n="btnSubmit">GENERATE COMPLETE RENDER</button>
                    </div>
                </form>

                <div id="statusBox"></div>
            </div>

            <!-- Right: TikTok Preview -->
            <div class="preview-col preview-sticky">
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left" data-i18n="previewTitle">📱 9:16 TikTok Preview</div>
                        <div style="font-size: 0.8rem; font-weight: normal;">
                            <label style="display:inline-flex; align-items:center; gap:5px; margin:0; cursor:pointer;">
                                <input type="checkbox" id="toggleSafeZone" onchange="toggleSafeZoneGuide()">
                                <span data-i18n="safeZoneToggle">Safe Zone Guide</span>
                            </label>
                        </div>
                    </div>

                    <div class="phone-wrapper" id="phoneWrapper">
                        <video id="previewPlayer" class="phone-video-bg" controls autoplay loop playsinline></video>

                        <div class="tiktok-overlay" id="tiktokOverlay">
                            <div class="tt-top">
                                <div style="width:20px;"></div>
                                <div class="tt-tabs">
                                    <span class="tt-tab-following">Following</span>
                                    <span class="tt-tab-foryou">For You</span>
                                </div>
                                <div style="font-size:1.1rem;">🔍</div>
                            </div>

                            <div class="tt-right">
                                <div class="tt-avatar"><div class="tt-avatar-plus">+</div></div>
                                <div class="tt-action"><div class="tt-icon">🤍</div><span>999.0K</span></div>
                                <div class="tt-action"><div class="tt-icon">💬</div><span>2463</span></div>
                                <div class="tt-action"><div class="tt-icon">🔖</div><span>60.5K</span></div>
                                <div class="tt-action"><div class="tt-icon">↗️</div><span>2230</span></div>
                                <div class="tt-disc"></div>
                            </div>

                            <div class="tt-bottom-left">
                                <div class="tt-user">@username</div>
                                <div class="tt-desc">Your viral TikTok video clip description #shorts #viral</div>
                                <div style="font-size: 0.65rem; color: rgba(255,255,255,0.7); margin-top:2px;">see translation</div>
                                <div class="tt-music">♫ Original Sound - TikTok Creator</div>
                            </div>

                            <div class="tt-bottom-bar">
                                <div class="tt-nav-item tt-nav-active"><span style="font-size:0.95rem;">🏠</span><span>Home</span></div>
                                <div class="tt-nav-item" style="position:relative;"><span style="font-size:0.95rem;">👥</span><span>Friends</span><span style="position:absolute; top:-2px; right:-6px; background:#ff004f; color:#fff; font-size:0.55rem; padding:1px 3px; border-radius:8px;">19</span></div>
                                <div class="tt-nav-item"><div class="tt-add-btn">+</div></div>
                                <div class="tt-nav-item" style="position:relative;"><span style="font-size:0.95rem;">💬</span><span>Inbox</span><span style="position:absolute; top:0px; right:0px; background:#ff004f; width:5px; height:5px; border-radius:50%;"></span></div>
                                <div class="tt-nav-item"><span style="font-size:0.95rem;">👤</span><span>Profile</span></div>
                            </div>
                        </div>

                        <div class="safe-zone-guide" id="safeZoneGuide">
                            <div class="safe-zone-label" data-i18n="safeZoneLabel">SUBTITLES SAFE ZONE</div>
                        </div>

                        <div class="mockup-sub-container" id="mockupContainer">
                            <div class="mockup-sub-text" id="mockupText"></div>
                        </div>
                    </div>

                    <button type="button" class="btn-preview" id="btnTestPreview" onclick="generateVideoPreview()">
                        <span>🎬</span> <b data-i18n="btnPreview">Preview On My Video (3s Clip)</b>
                    </button>
                    <p style="font-size:0.75rem; color:var(--text-dim); text-align:center;" data-i18n="previewDesc">
                        Renders the first 3 seconds of your actual video with RTX GPU in ~0.5s.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <!-- ================= VIEW 2: REFRAME STUDIO (16:9 -> 9:16) ================= -->
    <div id="viewReframe" class="view-section">
        <div class="main-layout">
            <div class="controls-col">
                <!-- 1. Framing Mode -->
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left">
                            <span>📐</span> <span data-i18n="reframeTitle">Reframe Studio (16:9 → 9:16)</span>
                        </div>
                    </div>

                    <div class="form-group">
                        <label data-i18n="sourceVideoLabel">Source 16:9 Video:</label>
                        <div class="file-control-row">
                            <button type="button" class="btn-pill" onclick="browseFile('reframe_video')">
                                📁 <span data-i18n="browseVideo">Browse Video...</span>
                            </button>
                            <div class="file-badge" id="reframeVideoBadge" data-i18n="noVideoSelected">No video selected</div>
                        </div>
                    </div>

                    <div class="form-group" style="margin-top:16px;">
                        <label data-i18n="framingModeLabel">Framing Mode:</label>
                        <select id="reframeMode" onchange="updateReframePreview()">
                            <option value="face_track" selected data-i18n="optFaceTrack">🎯 Auto Face Tracking (Smart Pan on Speaker)</option>
                            <option value="split_screen" data-i18n="optSplitScreen">👥 Podcast / Split-Screen (Stacked Top & Bottom)</option>
                            <option value="blurred_bg" data-i18n="optBlurredBg">🌌 Blurred Background (16:9 Center + Blown Blur)</option>
                            <option value="center" data-i18n="optCenterCrop">⏹️ Fixed Center Crop</option>
                            <option value="manual" data-i18n="optManualPan">🖐️ Manual Pan Slider</option>
                        </select>
                    </div>

                    <div class="form-group" id="manualPanGroup" style="display:none;">
                        <label data-i18n="manualPanLabel">Manual Camera Pan (Left → Right):</label>
                        <div class="slider-group">
                            <input type="range" id="manualPan" min="0" max="100" value="50" oninput="updateReframePreview()">
                            <span class="slider-val" id="manualPanVal">50%</span>
                        </div>
                    </div>
                </div>

                <!-- 2. Video Grading & Adjustments -->
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left">
                            <span>✨</span> <span data-i18n="gradingTitle">Video Grading & Enhancements</span>
                        </div>
                    </div>

                    <div class="row">
                        <div class="form-group">
                            <label data-i18n="sharpnessLabel">Sharpness (Nettoyage):</label>
                            <div class="slider-group">
                                <input type="range" id="sharpness" min="0" max="100" value="30" oninput="updateReframePreview()">
                                <span class="slider-val" id="sharpnessVal">30%</span>
                            </div>
                        </div>
                        <div class="form-group">
                            <label data-i18n="contrastLabel">Contrast:</label>
                            <div class="slider-group">
                                <input type="range" id="contrast" min="-50" max="50" value="8" oninput="updateReframePreview()">
                                <span class="slider-val" id="contrastVal">+8%</span>
                            </div>
                        </div>
                    </div>

                    <div class="row">
                        <div class="form-group">
                            <label data-i18n="saturationLabel">Saturation (Vibrant):</label>
                            <div class="slider-group">
                                <input type="range" id="saturation" min="-50" max="50" value="15" oninput="updateReframePreview()">
                                <span class="slider-val" id="saturationVal">+15%</span>
                            </div>
                        </div>
                        <div class="form-group">
                            <label data-i18n="brightnessLabel">Brightness:</label>
                            <div class="slider-group">
                                <input type="range" id="brightness" min="-30" max="30" value="0" oninput="updateReframePreview()">
                                <span class="slider-val" id="brightnessVal">0%</span>
                            </div>
                        </div>
                    </div>

                    <div class="form-group">
                        <label data-i18n="vignetteLabel">Vignette (Focus border):</label>
                        <div class="slider-group">
                            <input type="range" id="vignette" min="0" max="100" value="0" oninput="updateReframePreview()">
                            <span class="slider-val" id="vignetteVal">0%</span>
                        </div>
                    </div>
                </div>

                <!-- 3. Finish Action -->
                <div class="card">
                    <button type="button" class="btn-submit btn-reframe-submit" id="btnApplyReframe" onclick="applyAndReturnToSubtitles()">
                        💾 <span data-i18n="btnApplyReframe">Apply Reframe & Return To Subtitles</span>
                    </button>
                </div>

                <div id="reframeStatusBox" style="display:none;" class="card"></div>
            </div>

            <!-- Right: Reframe 9:16 Video Player -->
            <div class="preview-col preview-sticky">
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left" data-i18n="reframePreviewTitle">📱 9:16 Reframed Output Preview</div>
                    </div>

                    <div class="phone-wrapper" id="reframePhoneWrapper">
                        <video id="reframePlayer" class="reframe-phone-video" controls autoplay loop playsinline></video>
                        <div id="reframeVignetteOverlay" class="reframe-vignette-overlay"></div>
                        <div id="reframeModeBadge" class="reframe-mode-badge">🎯 Smart Face Track</div>
                        <div id="reframePlaceholder" class="reframe-placeholder">
                            <div class="reframe-ph-icon">📐</div>
                            <div class="reframe-ph-title" data-i18n="reframePlaceholderTitle">9:16 Canvas Ready</div>
                            <div class="reframe-ph-desc" data-i18n="reframePlaceholderText">Select a video and click "Preview Reframed Clip" to inspect AI framing & adjustments.</div>
                        </div>
                    </div>

                    <button type="button" class="btn-preview" id="btnTestReframePreview" onclick="generateReframe3sPreview()">
                        <span>🎬</span> <b data-i18n="btnPreviewReframe">Preview Reframed Clip (3s)</b>
                    </button>
                    <p style="font-size:0.75rem; color:var(--text-dim); text-align:center;" data-i18n="previewReframeDesc">
                        Fast GPU render with face tracking & color grading in ~0.5s.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Bilingual Dictionary
        const I18N = {
            en: {
                section1Title: "📁 1. Video & Subtitles",
                videoLabel: "9:16 Video (MP4 / MOV):",
                browseVideo: "Browse Video...",
                reframeBtn: "Reframe",
                noVideoSelected: "No video selected",
                transcribeCheckbox: "🎙️ <b>Transcribe with Local Whisper</b> (large-v3-turbo on RTX GPU)",
                srtLabel: "Existing SRT Subtitles (e.g. Buzz Whisper):",
                browseSrt: "Browse SRT...",
                noSrtSelected: "No SRT selected",
                langLabel: "Audio Language:",
                modelLabel: "Whisper Model:",
                section2Title: "🎨 2. Style Preset & Pacing",
                presetLabel: "Style Preset:",
                wordsPerChunkLabel: "Words Per Screen:",
                animationLabel: "Animation:",
                verticalPosLabel: "Vertical Position (Height):",
                advancedTitle: "⚙️ ADVANCED MODE (Full Customization)",
                highlightColorLabel: "Active Word (Highlight):",
                primaryColorLabel: "Base Text Color:",
                outlineColorLabel: "Outline Color:",
                outlineWidthLabel: "Outline Thickness:",
                shadowDepthLabel: "Shadow Depth:",
                glowLabel: "Glow / Neon Blur:",
                fontFamilyLabel: "Font Family:",
                fontSizeLabel: "Font Size:",
                animSpeedLabel: "Bounce / Pop Speed (ms):",
                animScaleLabel: "Peak Pop Scale (%):",
                allCapsLabel: "<b>Force ALL CAPS (Uppercase)</b>",
                section3Title: "🚀 3. Render & Export",
                renderFormatLabel: "Export Format:",
                optBurn: "🎬 Burned Video (Full MP4 with embedded subtitles via RTX GPU)",
                optProres: "✨ Transparent ProRes 4444 Overlay (.MOV for CapCut / Premiere)",
                optWebm: "🌐 Transparent WebM Overlay (.webm)",
                optBoth: "⚡ Both (Burned MP4 + Transparent ProRes)",
                btnSubmit: "GENERATE COMPLETE RENDER",
                previewTitle: "📱 9:16 TikTok Preview",
                safeZoneToggle: "Safe Zone Guide",
                safeZoneLabel: "SUBTITLES SAFE ZONE",
                btnPreview: "Preview On My Video (3s Clip)",
                previewDesc: "Renders the first 3 seconds of your actual video with RTX GPU in ~0.5s.",
                backToSubs: "Back to Subtitles",
                reframeTitle: "Reframe Studio (16:9 → 9:16)",
                sourceVideoLabel: "Source 16:9 Video:",
                framingModeLabel: "Framing Mode:",
                optFaceTrack: "🎯 Auto Face Tracking (Smart Pan on Speaker)",
                optSplitScreen: "👥 Podcast / Split-Screen (Stacked Top & Bottom)",
                optBlurredBg: "🌌 Blurred Background (16:9 Center + Blown Blur)",
                optCenterCrop: "⏹️ Fixed Center Crop",
                optManualPan: "🖐️ Manual Pan Slider",
                manualPanLabel: "Manual Camera Pan (Left → Right):",
                gradingTitle: "Video Grading & Enhancements",
                sharpnessLabel: "Sharpness (Nettoyage):",
                contrastLabel: "Contrast:",
                saturationLabel: "Saturation (Vibrant):",
                brightnessLabel: "Brightness:",
                vignetteLabel: "Vignette (Focus border):",
                btnApplyReframe: "Apply Reframe & Return To Subtitles",
                reframePreviewTitle: "📱 9:16 Reframed Output Preview",
                reframePlaceholderTitle: "9:16 Canvas Ready",
                reframePlaceholderText: "Select a video and click \"Preview Reframed Clip\" to inspect AI framing & adjustments.",
                btnPreviewReframe: "Preview Reframed Clip (3s)",
                previewReframeDesc: "Fast GPU render with face tracking & color grading in ~0.5s.",
                statusStart: "[*] Processing started locally...",
                successMsg: "🎉 SUCCESS!",
                errorMsg: "❌ ERROR:"
            },
            fr: {
                section1Title: "📁 1. Vidéo & Sous-titres",
                videoLabel: "Vidéo 9:16 (MP4 / MOV) :",
                browseVideo: "Parcourir Vidéo...",
                reframeBtn: "Reframe",
                noVideoSelected: "Aucune vidéo sélectionnée",
                transcribeCheckbox: "🎙️ <b>Générer avec Whisper local</b> (large-v3-turbo sur GPU RTX)",
                srtLabel: "Fichier SRT existant (ex: export Buzz Whisper) :",
                browseSrt: "Parcourir SRT...",
                noSrtSelected: "Aucun SRT sélectionné",
                langLabel: "Langue audio :",
                modelLabel: "Modèle Whisper :",
                section2Title: "🎨 2. Modèle de Style & Pacing",
                presetLabel: "Preset de Style :",
                wordsPerChunkLabel: "Mots par écran :",
                animationLabel: "Animation :",
                verticalPosLabel: "Position Verticale (Hauteur) :",
                advancedTitle: "⚙️ MODE AVANCÉ (Personnalisation complète)",
                highlightColorLabel: "Mot actif (Surbrillance) :",
                primaryColorLabel: "Texte normal (Base) :",
                outlineColorLabel: "Couleur du contour :",
                outlineWidthLabel: "Épaisseur du contour :",
                shadowDepthLabel: "Profondeur d'ombre :",
                glowLabel: "Lueur / Glow (Flou néon) :",
                fontFamilyLabel: "Police d'écriture :",
                fontSizeLabel: "Taille de police :",
                animSpeedLabel: "Vitesse du rebond / pop (ms) :",
                animScaleLabel: "Zoom / Échelle du rebond (%) :",
                allCapsLabel: "<b>Forcer tout en MAJUSCULES (ALL CAPS)</b>",
                section3Title: "🚀 3. Rendu & Export",
                renderFormatLabel: "Format d'exportation :",
                optBurn: "🎬 Rendu complet (MP4 avec sous-titres incrustés via GPU RTX)",
                optProres: "✨ Overlay Transparent ProRes 4444 (.MOV pour CapCut / Premiere)",
                optWebm: "🌐 Overlay Transparent WebM (.webm)",
                optBoth: "⚡ Les deux (MP4 incrusté + Overlay ProRes)",
                btnSubmit: "GÉNÉRER LE RENDU COMPLET",
                previewTitle: "📱 Aperçu 9:16 TikTok",
                safeZoneToggle: "Guide Safe Zone",
                safeZoneLabel: "ZONE IDÉALE SOUS-TITRES",
                btnPreview: "Prévisualiser sur ma vidéo (Extrait 3s)",
                previewDesc: "Génère les 3 premières secondes de votre vraie vidéo avec GPU RTX en ~0.5s.",
                backToSubs: "Retour aux Sous-titres",
                reframeTitle: "Studio Reframe (16:9 → 9:16)",
                sourceVideoLabel: "Vidéo 16:9 Source :",
                framingModeLabel: "Mode de Cadrage :",
                optFaceTrack: "🎯 Suivi Automatique du Visage (Smart Pan)",
                optSplitScreen: "👥 Podcast / Split-Screen (Empilement Haut / Bas)",
                optBlurredBg: "🌌 Fond Flouté (16:9 au centre + arrière-plan flou)",
                optCenterCrop: "⏹️ Centré Fixe",
                optManualPan: "🖐️ Balayage Manuel (Slider)",
                manualPanLabel: "Cadrage Manuel (Gauche → Droite) :",
                gradingTitle: "Ajustements & Retouches Vidéo",
                sharpnessLabel: "Netteté (Nettoyage) :",
                contrastLabel: "Contraste :",
                saturationLabel: "Saturation (Vibrant) :",
                brightnessLabel: "Luminosité :",
                vignetteLabel: "Vignettage (Assombrir bords) :",
                btnApplyReframe: "Appliquer le Reframe & Revenir aux Sous-titres",
                reframePreviewTitle: "📱 Aperçu du Rendu 9:16",
                reframePlaceholderTitle: "Canevas 9:16 Prêt",
                reframePlaceholderText: "Sélectionnez une vidéo et cliquez sur \"Prévisualiser l'extrait\" pour inspecter le cadrage IA et les retouches.",
                btnPreviewReframe: "Prévisualiser l'extrait (3s)",
                previewReframeDesc: "Rendu GPU rapide avec détection faciale & retouches en ~0.5s.",
                statusStart: "[*] Lancement du traitement local...",
                successMsg: "🎉 SUCCÈS !",
                errorMsg: "❌ ERREUR :"
            }
        };

        let currentLang = localStorage.getItem('submaxxing_lang') || 'en';

        function setLanguage(lang) {
            currentLang = lang;
            localStorage.setItem('submaxxing_lang', lang);

            document.getElementById('btnLangEN').className = 'lang-btn' + (lang === 'en' ? ' active' : '');
            document.getElementById('btnLangFR').className = 'lang-btn' + (lang === 'fr' ? ' active' : '');

            const dict = I18N[lang];
            document.querySelectorAll('[data-i18n]').forEach(el => {
                const key = el.getAttribute('data-i18n');
                if (dict[key]) {
                    el.innerHTML = dict[key];
                }
            });

            updateMockup();
        }

        // View Switcher (Subtitles <-> Reframe)
        function switchView(viewName) {
            document.getElementById('viewSubtitles').className = 'view-section' + (viewName === 'subtitles' ? ' active' : '');
            document.getElementById('viewReframe').className = 'view-section' + (viewName === 'reframe' ? ' active' : '');
            document.getElementById('navBackBtn').style.display = (viewName === 'reframe') ? 'inline-flex' : 'none';

            const badge = document.getElementById('brandBadge');
            if (viewName === 'reframe') {
                document.body.classList.add('theme-reframe');
                if (badge) badge.innerText = 'REFRAME STUDIO';
                const currentVid = document.getElementById('videoPath').value;
                if (currentVid) {
                    setReframeVideo(currentVid);
                }
                updateReframePreview();
            } else {
                document.body.classList.remove('theme-reframe');
                if (badge) badge.innerText = 'STUDIO PRO';
                updateMockup();
            }
        }

        function openReframeView() {
            const currentVid = document.getElementById('videoPath').value;
            if (currentVid) {
                setReframeVideo(currentVid);
            }
            switchView('reframe');
        }

        function setReframeVideo(fullPath) {
            document.getElementById('videoPath').value = fullPath;
            const filename = fullPath.split(/[/\\\\]/).pop();
            const badge = document.getElementById('reframeVideoBadge');
            badge.innerText = '🎬 ' + filename;
            badge.className = 'file-badge has-file';
        }

        // Browse Native Windows Dialog
        async function browseFile(type) {
            try {
                const targetType = (type === 'srt') ? 'srt' : 'video';
                const res = await fetch(`/api/browse?type=${targetType}`, { method: 'POST' });
                const data = await res.json();
                if (data.path) {
                    const filename = data.path.split(/[/\\\\]/).pop();
                    if (type === 'video') {
                        document.getElementById('videoPath').value = data.path;
                        const badge = document.getElementById('videoBadge');
                        badge.innerText = '🎬 ' + filename;
                        badge.className = 'file-badge has-file';
                    } else if (type === 'srt') {
                        document.getElementById('srtPath').value = data.path;
                        const badge = document.getElementById('srtBadge');
                        badge.innerText = '📄 ' + filename;
                        badge.className = 'file-badge has-file';
                    } else if (type === 'reframe_video') {
                        setReframeVideo(data.path);
                    }
                }
            } catch (err) {
                alert("File Explorer error: " + err.message);
            }
        }

        // Toggle Whisper controls
        const autoTranscribeCheck = document.getElementById('autoTranscribe');
        const srtGroup = document.getElementById('srtGroup');
        const whisperGroup = document.getElementById('whisperGroup');

        autoTranscribeCheck.addEventListener('change', () => {
            if (autoTranscribeCheck.checked) {
                srtGroup.style.display = 'none';
                whisperGroup.style.display = 'grid';
            } else {
                srtGroup.style.display = 'block';
                whisperGroup.style.display = 'none';
            }
        });

        // Toggle Advanced Accordion
        function toggleAdvanced() {
            const adv = document.getElementById('advancedContent');
            const chev = document.getElementById('advChevron');
            if (adv.style.display === 'block') {
                adv.style.display = 'none';
                chev.innerText = '▼';
            } else {
                adv.style.display = 'block';
                chev.innerText = '▲';
            }
        }

        function toggleSafeZoneGuide() {
            const guide = document.getElementById('safeZoneGuide');
            guide.style.display = document.getElementById('toggleSafeZone').checked ? 'block' : 'none';
        }

        // Sync Colors
        function syncColor(type) {
            const c = document.getElementById(type + 'Color').value;
            document.getElementById(type + 'ColorHex').value = c.toUpperCase();
            updateMockup();
        }
        function syncColorHex(type) {
            const hex = document.getElementById(type + 'ColorHex').value;
            if (/^#[0-9A-Fa-f]{6}$/.test(hex)) {
                document.getElementById(type + 'Color').value = hex;
                updateMockup();
            }
        }

        // Presets definitions
        const PRESETS = {
            hormozi: {
                highlight: "#FFE600", primary: "#FFFFFF", outline: "#000000", outlineWidth: 5.5,
                shadow: "#000000", shadowDepth: 3.0, glow: 0.0, font: "Montserrat ExtraBold",
                size: 82, anim: "bounce", speed: 100, scale: 118, allCaps: true
            },
            mrbeast: {
                highlight: "#FFFFFF", primary: "#FFE600", outline: "#000000", outlineWidth: 6.0,
                shadow: "#000000", shadowDepth: 3.5, glow: 0.0, font: "Impact",
                size: 88, anim: "pop", speed: 80, scale: 114, allCaps: true
            },
            neon_glow: {
                highlight: "#00FFCC", primary: "#FFFFFF", outline: "#002B20", outlineWidth: 4.0,
                shadow: "#00FFCC", shadowDepth: 0.0, glow: 5.0, font: "Montserrat ExtraBold",
                size: 80, anim: "pop", speed: 90, scale: 112, allCaps: true
            },
            tiktok_bold: {
                highlight: "#00FF66", primary: "#FFFFFF", outline: "#000000", outlineWidth: 5.0,
                shadow: "#00FF66", shadowDepth: 2.5, glow: 0.0, font: "The Bold Font",
                size: 84, anim: "bounce", speed: 100, scale: 118, allCaps: true
            },
            cyberpunk: {
                highlight: "#FF007F", primary: "#00FFFF", outline: "#000000", outlineWidth: 5.5,
                shadow: "#FF007F", shadowDepth: 0.0, glow: 3.5, font: "Impact",
                size: 84, anim: "bounce", speed: 90, scale: 120, allCaps: true
            },
            fire_red: {
                highlight: "#FF2200", primary: "#FFFFFF", outline: "#000000", outlineWidth: 5.5,
                shadow: "#000000", shadowDepth: 3.0, glow: 0.0, font: "Montserrat ExtraBold",
                size: 82, anim: "pop", speed: 85, scale: 115, allCaps: true
            },
            clean_minimal: {
                highlight: "#FF3366", primary: "#FFFFFF", outline: "#101010", outlineWidth: 3.5,
                shadow: "#000000", shadowDepth: 2.0, glow: 0.0, font: "Arial",
                size: 74, anim: "fade", speed: 80, scale: 100, allCaps: false
            }
        };

        function applyPresetToControls() {
            const key = document.getElementById('stylePreset').value;
            const p = PRESETS[key] || PRESETS.hormozi;

            document.getElementById('highlightColor').value = p.highlight;
            document.getElementById('highlightColorHex').value = p.highlight;
            document.getElementById('primaryColor').value = p.primary;
            document.getElementById('primaryColorHex').value = p.primary;
            document.getElementById('outlineColor').value = p.outline;
            document.getElementById('outlineColorHex').value = p.outline;

            document.getElementById('outlineWidth').value = p.outlineWidth;
            document.getElementById('shadowDepth').value = p.shadowDepth;
            document.getElementById('glow').value = p.glow;
            document.getElementById('fontName').value = p.font;
            document.getElementById('fontSize').value = p.size;
            document.getElementById('animation').value = p.anim;
            document.getElementById('animSpeed').value = p.speed;
            document.getElementById('animScale').value = p.scale;
            document.getElementById('allCaps').checked = p.allCaps;

            updateMockup();
        }

        // Live Subtitles Mockup Render Loop
        const mockupContainer = document.getElementById('mockupContainer');
        const mockupText = document.getElementById('mockupText');
        const previewPlayer = document.getElementById('previewPlayer');

        let currentWordIndex = 0;
        function updateMockup() {
            const posY = parseInt(document.getElementById('posY').value);
            const outlineW = parseFloat(document.getElementById('outlineWidth').value);
            const shadowD = parseFloat(document.getElementById('shadowDepth').value);
            const glowVal = parseFloat(document.getElementById('glow').value);
            const fontSize = parseInt(document.getElementById('fontSize').value);
            const animSpeed = parseInt(document.getElementById('animSpeed').value);
            const animScale = parseInt(document.getElementById('animScale').value);
            const animType = document.getElementById('animation').value;
            const allCaps = document.getElementById('allCaps').checked;
            const wordsPerChunk = parseInt(document.getElementById('wordsPerChunk').value);
            const fontName = document.getElementById('fontName').value;

            const highlight = document.getElementById('highlightColor').value;
            const primary = document.getElementById('primaryColor').value;
            const outline = document.getElementById('outlineColor').value;

            document.getElementById('posYVal').innerText = `${posY}px`;
            document.getElementById('outlineWidthVal').innerText = `${outlineW}px`;
            document.getElementById('shadowDepthVal').innerText = `${shadowD}px`;
            document.getElementById('glowVal').innerText = `${glowVal}`;
            document.getElementById('fontSizeVal').innerText = `${fontSize}px`;
            document.getElementById('animSpeedVal').innerText = `${animSpeed}ms`;
            document.getElementById('animScaleVal').innerText = `${animScale}%`;

            const scaledBottom = Math.round((posY / 1920) * 586);
            mockupContainer.style.bottom = `${scaledBottom}px`;

            const scaledFontSize = Math.round((fontSize / 1920) * 586);
            mockupText.style.fontFamily = `'${fontName}', sans-serif`;
            mockupText.style.fontSize = `${scaledFontSize}px`;
            mockupText.style.fontWeight = '900';
            mockupText.style.textTransform = allCaps ? 'uppercase' : 'none';

            const scaledStroke = Math.max(1, Math.round((outlineW / 1920) * 586 * 1.5));
            mockupText.style.webkitTextStroke = `${scaledStroke}px ${outline}`;

            const scaledShadow = Math.round((shadowD / 1920) * 586 * 1.5);
            mockupText.style.textShadow = scaledShadow > 0 ? `${scaledShadow}px ${scaledShadow}px 0px ${outline}` : 'none';
            mockupText.style.filter = glowVal > 0 ? `drop-shadow(0 0 ${glowVal * 2}px ${highlight})` : 'none';

            let sampleWords = currentLang === 'fr' 
                ? ["C'EST", "VRAIMENT", "FOU", "TIKTOK"].slice(0, wordsPerChunk)
                : ["THIS", "IS", "TOTALLY", "INSANE"].slice(0, wordsPerChunk);

            if (!allCaps) {
                sampleWords = currentLang === 'fr'
                    ? ["C'est", "vraiment", "fou", "TikTok"].slice(0, wordsPerChunk)
                    : ["This", "is", "totally", "insane"].slice(0, wordsPerChunk);
            }

            const activeIdx = currentWordIndex % sampleWords.length;

            const html = sampleWords.map((w, idx) => {
                const isActive = (idx === activeIdx);
                const color = isActive ? highlight : primary;

                let transformStyle = "";
                let opacityStyle = "opacity: 1;";

                if (isActive) {
                    if (animType === "bounce" || animType === "pop") {
                        transformStyle = `transform: scale(${animScale / 100}); transition: transform ${animSpeed}ms cubic-bezier(0.175, 0.885, 0.32, 1.275);`;
                    } else if (animType === "fade") {
                        opacityStyle = `opacity: 1; transition: opacity ${animSpeed}ms ease-in;`;
                    }
                } else {
                    transformStyle = "transform: scale(1.0);";
                    if (animType === "fade") {
                        opacityStyle = "opacity: 0.85;";
                    }
                }

                return `<span style="color:${color}; display:inline-block; margin:0 4px; ${transformStyle} ${opacityStyle}">${w}</span>`;
            }).join(' ');

            mockupText.innerHTML = html;
        }

        setInterval(() => {
            currentWordIndex++;
            updateMockup();
        }, 550);

        // Subtitles 3-Second Video Preview
        async function generateVideoPreview() {
            const video = document.getElementById('videoPath').value.trim();
            const srt = document.getElementById('srtPath').value.trim();
            const autoTranscribe = autoTranscribeCheck.checked;

            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo MP4." : "Please select an MP4 video first.");
                return;
            }

            const btn = document.getElementById('btnTestPreview');
            btn.disabled = true;
            btn.innerHTML = currentLang === 'fr' ? "⏳ Rendu extrait 3s (GPU RTX)..." : "⏳ Rendering 3s preview (RTX GPU)...";

            const payload = {
                video: video,
                srt: srt,
                autoTranscribe: autoTranscribe,
                lang: document.getElementById('lang').value,
                model: document.getElementById('model').value,
                style: document.getElementById('stylePreset').value,
                wordsPerChunk: parseInt(document.getElementById('wordsPerChunk').value),
                animation: document.getElementById('animation').value,
                posY: parseInt(document.getElementById('posY').value),
                highlightColor: document.getElementById('highlightColor').value,
                primaryColor: document.getElementById('primaryColor').value,
                outlineColor: document.getElementById('outlineColor').value,
                outlineWidth: parseFloat(document.getElementById('outlineWidth').value),
                shadowColor: document.getElementById('outlineColor').value,
                shadowDepth: parseFloat(document.getElementById('shadowDepth').value),
                glow: parseFloat(document.getElementById('glow').value),
                fontName: document.getElementById('fontName').value,
                fontSize: parseInt(document.getElementById('fontSize').value),
                animSpeed: parseInt(document.getElementById('animSpeed').value),
                animScale: parseInt(document.getElementById('animScale').value),
                allCaps: document.getElementById('allCaps').checked
            };

            try {
                const res = await fetch('/api/preview_video', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    mockupContainer.style.display = 'none';
                    previewPlayer.style.display = 'block';
                    previewPlayer.src = `/api/get_preview_video?t=${Date.now()}`;
                    previewPlayer.play();
                } else {
                    alert("Error: " + data.error);
                }
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<span>🎬</span> <b>${I18N[currentLang].btnPreview}</b>`;
            }
        }

        // Full Subtitles Render Submission
        document.getElementById('subForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btnSubmit = document.getElementById('btnSubmit');
            const statusBox = document.getElementById('statusBox');

            const video = document.getElementById('videoPath').value.trim();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo." : "Please select a video first.");
                return;
            }

            btnSubmit.disabled = true;
            btnSubmit.innerText = currentLang === 'fr' ? "⏳ RENDU COMPLET EN COURS..." : "⏳ RENDERING FULL VIDEO (GPU ACCELERATED)...";
            statusBox.style.display = "block";
            statusBox.innerText = I18N[currentLang].statusStart;

            const payload = {
                video: video,
                autoTranscribe: autoTranscribeCheck.checked,
                srt: document.getElementById('srtPath').value.trim(),
                lang: document.getElementById('lang').value,
                model: document.getElementById('model').value,
                style: document.getElementById('stylePreset').value,
                wordsPerChunk: parseInt(document.getElementById('wordsPerChunk').value),
                animation: document.getElementById('animation').value,
                posY: parseInt(document.getElementById('posY').value),
                renderType: document.getElementById('renderType').value,
                highlightColor: document.getElementById('highlightColor').value,
                primaryColor: document.getElementById('primaryColor').value,
                outlineColor: document.getElementById('outlineColor').value,
                outlineWidth: parseFloat(document.getElementById('outlineWidth').value),
                shadowColor: document.getElementById('outlineColor').value,
                shadowDepth: parseFloat(document.getElementById('shadowDepth').value),
                glow: parseFloat(document.getElementById('glow').value),
                fontName: document.getElementById('fontName').value,
                fontSize: parseInt(document.getElementById('fontSize').value),
                animSpeed: parseInt(document.getElementById('animSpeed').value),
                animScale: parseInt(document.getElementById('animScale').value),
                allCaps: document.getElementById('allCaps').checked
            };

            try {
                const res = await fetch('/api/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    statusBox.innerText = I18N[currentLang].successMsg + "\\n\\n" + data.logs;
                } else {
                    statusBox.innerText = I18N[currentLang].errorMsg + "\\n\\n" + (data.error || "An error occurred.");
                }
            } catch (err) {
                statusBox.innerText = I18N[currentLang].errorMsg + " " + err.message;
            } finally {
                btnSubmit.disabled = false;
                btnSubmit.innerText = I18N[currentLang].btnSubmit;
            }
        });

        // ================= REFRAME STUDIO LOGIC =================
        function updateReframePreview() {
            const mode = document.getElementById('reframeMode').value;
            document.getElementById('manualPanGroup').style.display = (mode === 'manual') ? 'block' : 'none';

            const sharpness = parseInt(document.getElementById('sharpness').value);
            const contrast = parseInt(document.getElementById('contrast').value);
            const saturation = parseInt(document.getElementById('saturation').value);
            const brightness = parseInt(document.getElementById('brightness').value);
            const vignette = parseInt(document.getElementById('vignette').value);

            document.getElementById('sharpnessVal').innerText = `${sharpness}%`;
            document.getElementById('contrastVal').innerText = (contrast >= 0 ? '+' : '') + `${contrast}%`;
            document.getElementById('saturationVal').innerText = (saturation >= 0 ? '+' : '') + `${saturation}%`;
            document.getElementById('brightnessVal').innerText = (brightness >= 0 ? '+' : '') + `${brightness}%`;
            document.getElementById('vignetteVal').innerText = `${vignette}%`;

            // Live CSS Filter on player
            const player = document.getElementById('reframePlayer');
            const cVal = 1 + (contrast / 100);
            const sVal = 1 + (saturation / 100);
            const bVal = 1 + (brightness / 100);
            player.style.filter = `contrast(${cVal}) saturate(${sVal}) brightness(${bVal})`;

            // Live Vignette Overlay Shadow
            const vigOverlay = document.getElementById('reframeVignetteOverlay');
            if (vigOverlay) {
                if (vignette > 0) {
                    const blur = (vignette / 100) * 120 + 20;
                    const spread = (vignette / 100) * 60;
                    const opacity = Math.min(0.92, (vignette / 100) * 1.05);
                    vigOverlay.style.boxShadow = `inset 0 0 ${blur}px ${spread}px rgba(0, 0, 0, ${opacity})`;
                } else {
                    vigOverlay.style.boxShadow = 'none';
                }
            }

            // Update Mode Badge text
            const modeBadge = document.getElementById('reframeModeBadge');
            const modeNames = {
                face_track: '🎯 Smart Face Track',
                split_screen: '👥 Podcast Split-Screen',
                blurred_bg: '🌌 Blurred Background',
                center: '⏹️ Fixed Center',
                manual: '🖐️ Manual Pan'
            };
            if (modeBadge) modeBadge.innerText = modeNames[mode] || mode;
        }

        async function generateReframe3sPreview() {
            const video = document.getElementById('videoPath').value.trim();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez sélectionner une vidéo d'abord." : "Please select a video first.");
                return;
            }

            const btn = document.getElementById('btnTestReframePreview');
            btn.disabled = true;
            btn.innerHTML = currentLang === 'fr' ? "⏳ Rendu Reframe 3s (GPU)..." : "⏳ Rendering 3s Reframe (GPU)...";

            const payload = {
                video: video,
                mode: document.getElementById('reframeMode').value,
                manualPan: parseInt(document.getElementById('manualPan').value),
                sharpness: parseFloat(document.getElementById('sharpness').value) / 100.0,
                contrast: 1.0 + (parseFloat(document.getElementById('contrast').value) / 100.0),
                saturation: 1.0 + (parseFloat(document.getElementById('saturation').value) / 100.0),
                brightness: parseFloat(document.getElementById('brightness').value) / 100.0,
                vignette: parseFloat(document.getElementById('vignette').value) / 100.0,
                previewOnly: true
            };

            try {
                const res = await fetch('/api/reframe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    document.getElementById('reframePlaceholder').style.display = 'none';
                    const player = document.getElementById('reframePlayer');
                    player.style.display = 'block';
                    player.src = `/api/get_reframe_preview?t=${Date.now()}`;
                    player.load();
                    player.play().catch(() => {});
                } else {
                    alert("Error: " + data.error);
                }
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `<span>🎬</span> <b data-i18n="btnPreviewReframe">${I18N[currentLang].btnPreviewReframe}</b>`;
            }
        }

        async function applyAndReturnToSubtitles() {
            const video = document.getElementById('videoPath').value.trim();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez sélectionner une vidéo 16:9." : "Please select a 16:9 video first.");
                return;
            }

            const btn = document.getElementById('btnApplyReframe');
            btn.disabled = true;
            btn.innerHTML = currentLang === 'fr' ? "⏳ Rendu Reframe complet (GPU RTX)..." : "⏳ Rendering Full 9:16 Reframe (RTX GPU)...";

            const payload = {
                video: video,
                mode: document.getElementById('reframeMode').value,
                manualPan: parseInt(document.getElementById('manualPan').value),
                sharpness: parseFloat(document.getElementById('sharpness').value) / 100.0,
                contrast: 1.0 + (parseFloat(document.getElementById('contrast').value) / 100.0),
                saturation: 1.0 + (parseFloat(document.getElementById('saturation').value) / 100.0),
                brightness: parseFloat(document.getElementById('brightness').value) / 100.0,
                vignette: parseFloat(document.getElementById('vignette').value) / 100.0,
                previewOnly: false
            };

            try {
                const res = await fetch('/api/reframe', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success && data.outputPath) {
                    // Update main video path to newly reframed 9:16 video
                    document.getElementById('videoPath').value = data.outputPath;
                    const filename = data.outputPath.split(/[/\\\\]/).pop();
                    const badge = document.getElementById('videoBadge');
                    badge.innerText = '🎬 ' + filename + ' (9:16)';
                    badge.className = 'file-badge has-file';

                    alert(currentLang === 'fr' 
                        ? "Vidéo recadrée en 9:16 avec succès ! Vous pouvez maintenant appliquer vos sous-titres."
                        : "Video successfully reframed to 9:16! You can now apply your subtitles.");

                    switchView('subtitles');
                } else {
                    alert("Error: " + (data.error || "Reframe failed"));
                }
            } catch (err) {
                alert("Error: " + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = `💾 <span data-i18n="btnApplyReframe">${I18N[currentLang].btnApplyReframe}</span>`;
            }
        }

        // Init language and controls
        setLanguage(currentLang);
        applyPresetToControls();
        updateReframePreview();
    </script>
</body>
</html>
"""


def native_file_picker(file_type="video") -> str:
    """Opens a native Windows Open File dialog and returns the selected path."""
    import tkinter as tk
    from tkinter import filedialog
    root = tk.Tk()
    root.withdraw()
    root.wm_attributes("-topmost", 1)

    if file_type == "video":
        ft = [("Video Files", "*.mp4;*.mov;*.mkv;*.webm"), ("All Files", "*.*")]
        title = "Select Video"
    else:
        ft = [("Subtitle Files", "*.srt;*.vtt"), ("All Files", "*.*")]
        title = "Select SRT Subtitle File"

    selected = filedialog.askopenfilename(title=title, filetypes=ft)
    root.destroy()
    return selected or ""


def build_style_from_payload(data: dict) -> SubStylePreset:
    """Builds a SubStylePreset from the incoming web payload (supports all advanced overrides)."""
    style_name = data.get("style", "hormozi")
    preset = PRESETS.get(style_name, PRESETS["hormozi"])

    return SubStylePreset(
        name=preset.name,
        font_name=data.get("fontName") or preset.font_name,
        font_size=int(data.get("fontSize", preset.font_size)),
        primary_color=data.get("primaryColor") or preset.primary_color,
        highlight_color=data.get("highlightColor") or preset.highlight_color,
        outline_color=data.get("outlineColor") or preset.outline_color,
        outline_width=float(data.get("outlineWidth", preset.outline_width)),
        shadow_color=data.get("shadowColor") or preset.shadow_color,
        shadow_depth=float(data.get("shadowDepth", preset.shadow_depth)),
        blur=float(data.get("glow", preset.blur)),
        all_caps=bool(data.get("allCaps", preset.all_caps)),
        animation=data.get("animation") or preset.animation,
        anim_speed_ms=int(data.get("animSpeed", preset.anim_speed_ms)),
        anim_scale=int(data.get("animScale", preset.anim_scale)),
        margin_v=int(data.get("posY", preset.margin_v))
    )


class SubHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_CONTENT.encode("utf-8"))
        elif parsed.path in ["/api/get_preview_video", "/api/get_reframe_preview"]:
            target = PREVIEW_FILE if parsed.path == "/api/get_preview_video" else REFRAME_PREVIEW_FILE
            if os.path.exists(target):
                self._serve_video_file(target)
            else:
                self.send_response(404)
                self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)

        if parsed.path == "/api/browse":
            query = urllib.parse.parse_qs(parsed.query)
            ftype = query.get("type", ["video"])[0]
            selected_path = native_file_picker(ftype)
            self._send_json({"path": selected_path})
            return

        elif parsed.path == "/api/preview_video":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            self._handle_preview(data)
            return

        elif parsed.path == "/api/process":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            self._handle_full_render(data)
            return

        elif parsed.path == "/api/reframe":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            self._handle_reframe(data)
            return

    def _handle_preview(self, data: dict):
        try:
            video_path = data.get("video", "").strip(' "')
            srt_path = data.get("srt", "").strip(' "')
            auto_transcribe = data.get("autoTranscribe", False)
            words_per_chunk = data.get("wordsPerChunk", 2)
            lang = data.get("lang", "fr")
            model_name = data.get("model", "large-v3-turbo")

            if not os.path.exists(video_path):
                self._send_json({"success": False, "error": "Video file not found."})
                return

            vinfo = get_video_info(video_path)
            width, height = vinfo["width"], vinfo["height"]

            if auto_transcribe or not srt_path:
                from transcriber import transcribe_video
                chunks, _ = transcribe_video(
                    media_path=video_path,
                    model_name=model_name,
                    language=None if lang == "auto" else lang,
                    max_words=words_per_chunk
                )
            else:
                chunks = srt_to_chunks(srt_path, max_words=words_per_chunk, is_file=True)

            active_style = build_style_from_payload(data)

            ass_path = os.path.join(os.path.dirname(PREVIEW_FILE), "web_preview.ass")
            ass_content = chunks_to_ass(chunks, active_style, play_res_x=width, play_res_y=height)
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

            render_subtitles_to_video(
                video_path=video_path,
                ass_path=ass_path,
                output_path=PREVIEW_FILE,
                use_gpu=True,
                duration_limit=3.0
            )

            self._send_json({"success": True})
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_reframe(self, data: dict):
        try:
            video_path = data.get("video", "").strip(' "')
            if not os.path.exists(video_path):
                self._send_json({"success": False, "error": "Video file not found."})
                return

            preview_only = data.get("previewOnly", False)
            mode = data.get("mode", "face_track")
            manual_pan = data.get("manualPan", 50)
            sharpness = float(data.get("sharpness", 0.0))
            contrast = float(data.get("contrast", 1.0))
            saturation = float(data.get("saturation", 1.0))
            brightness = float(data.get("brightness", 0.0))
            vignette = float(data.get("vignette", 0.0))

            if preview_only:
                output_path = REFRAME_PREVIEW_FILE
                dur_limit = 3.0
            else:
                base_dir = os.path.dirname(video_path)
                base_name = os.path.splitext(os.path.basename(video_path))[0]
                output_path = os.path.join(base_dir, f"{base_name}_reframed_9x16.mp4")
                dur_limit = None

            process_reframe(
                video_path=video_path,
                output_path=output_path,
                mode=mode,
                manual_pan=manual_pan,
                sharpness=sharpness,
                contrast=contrast,
                saturation=saturation,
                brightness=brightness,
                vignette=vignette,
                duration_limit=dur_limit,
                use_gpu=True
            )

            self._send_json({"success": True, "outputPath": output_path})
        except Exception as e:
            import traceback
            print(f"[!] Reframe error: {traceback.format_exc()}")
            self._send_json({"success": False, "error": str(e)})

    def _handle_full_render(self, data: dict):
        logs = []
        def log(msg):
            logs.append(msg)
            print(msg)

        video_path = data.get("video", "").strip(' "')
        srt_path = data.get("srt", "").strip(' "')
        auto_transcribe = data.get("autoTranscribe", False)
        words_per_chunk = data.get("wordsPerChunk", 2)
        render_type = data.get("renderType", "burn")
        model_name = data.get("model", "large-v3-turbo")
        lang = data.get("lang", "fr")

        if not video_path or not os.path.exists(video_path):
            self._send_json({"success": False, "error": f"Video file not found: '{video_path}'"})
            return

        try:
            base_name = os.path.splitext(video_path)[0]
            ass_path = f"{base_name}_submaxxing.ass"

            log(f"[*] Reading video metadata: '{video_path}'...")
            vinfo = get_video_info(video_path)
            width, height, duration, fps = vinfo["width"], vinfo["height"], vinfo["duration"], vinfo["fps"]
            log(f"    Format: {width}x{height} | Duration: {duration:.2f}s | FPS: {fps:.2f}")

            if auto_transcribe or not srt_path:
                log(f"[*] Running local Whisper '{model_name}' on GPU (language: {lang})...")
                from transcriber import transcribe_video
                chunks, srt_content = transcribe_video(
                    media_path=video_path,
                    model_name=model_name,
                    language=None if lang == "auto" else lang,
                    max_words=words_per_chunk
                )
                saved_srt = f"{base_name}_transcribed.srt"
                with open(saved_srt, "w", encoding="utf-8") as f:
                    f.write(srt_content)
                log(f"[+] Saved generated SRT to: '{saved_srt}'")
            else:
                if not os.path.exists(srt_path):
                    self._send_json({"success": False, "error": f"SRT file not found: '{srt_path}'"})
                    return
                log(f"[*] Slicing SRT '{srt_path}' (max {words_per_chunk} words/chunk)...")
                chunks = srt_to_chunks(srt_path, max_words=words_per_chunk, is_file=True)
                log(f"[+] Sliced into {len(chunks)} chunks.")

            active_style = build_style_from_payload(data)

            log(f"[*] Generating ASS subtitle file ({active_style.name})...")
            ass_content = chunks_to_ass(chunks, active_style, play_res_x=width, play_res_y=height)
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
            log(f"[+] ASS file created: '{ass_path}'")

            if render_type in ["overlay_mov", "both"]:
                mov_out = f"{base_name}_overlay.mov"
                log(f"[*] Rendering transparent ProRes 4444 overlay...")
                render_transparent_overlay(
                    ass_path=ass_path,
                    output_path=mov_out,
                    duration=duration,
                    width=width,
                    height=height,
                    fps=fps,
                    format_type="mov"
                )
                log(f"[+] ProRes 4444 overlay ready: '{mov_out}'")

            if render_type == "overlay_webm":
                webm_out = f"{base_name}_overlay.webm"
                log(f"[*] Rendering transparent WebM overlay...")
                render_transparent_overlay(
                    ass_path=ass_path,
                    output_path=webm_out,
                    duration=duration,
                    width=width,
                    height=height,
                    fps=fps,
                    format_type="webm"
                )
                log(f"[+] WebM overlay ready: '{webm_out}'")

            if render_type in ["burn", "both"]:
                final_mp4 = f"{base_name}_subbed.mp4"
                log(f"[*] GPU NVENC accelerated rendering...")
                render_subtitles_to_video(
                    video_path=video_path,
                    ass_path=ass_path,
                    output_path=final_mp4,
                    use_gpu=True
                )
                log(f"[+] Final video rendered: '{final_mp4}'")

            log("\n🎉 Done successfully!")
            self._send_json({"success": True, "logs": "\n".join(logs)})

        except Exception as e:
            import traceback
            log(f"[!] Error: {traceback.format_exc()}")
            self._send_json({"success": False, "error": str(e), "logs": "\n".join(logs)})

    def _serve_video_file(self, file_path: str):
        size = os.path.getsize(file_path)
        range_header = self.headers.get("Range")
        if range_header:
            m = re.match(r"bytes=(\d+)-(\d*)", range_header)
            if m:
                start = int(m.group(1))
                end = int(m.group(2)) if m.group(2) else size - 1
                length = end - start + 1
                self.send_response(206)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
                self.send_header("Content-Length", str(length))
                self.send_header("Accept-Ranges", "bytes")
                self.end_headers()
                with open(file_path, "rb") as f:
                    f.seek(start)
                    self.wfile.write(f.read(length))
                return

        self.send_response(200)
        self.send_header("Content-Type", "video/mp4")
        self.send_header("Content-Length", str(size))
        self.send_header("Accept-Ranges", "bytes")
        self.end_headers()
        with open(file_path, "rb") as f:
            self.wfile.write(f.read())

    def _send_json(self, data: dict):
        self.send_response(200)
        self.send_header("Content-type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode("utf-8"))


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    allow_reuse_address = True
    daemon_threads = True


def run_server():
    server = None
    try:
        server = ThreadedHTTPServer(("127.0.0.1", PORT), SubHandler)
    except OSError:
        print(f"[!] Port {PORT} in use, clearing previous process...")
        try:
            import subprocess
            out = subprocess.check_output(f'netstat -ano | findstr :{PORT}', shell=True, text=True)
            for line in out.strip().splitlines():
                parts = line.strip().split()
                if len(parts) >= 5 and f":{PORT}" in parts[1]:
                    pid = parts[-1]
                    if pid != str(os.getpid()):
                        subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
            time.sleep(0.5)
            server = ThreadedHTTPServer(("127.0.0.1", PORT), SubHandler)
        except Exception:
            server = ThreadedHTTPServer(("127.0.0.1", 0), SubHandler)

    bound_port = server.server_address[1]
    url = f"http://127.0.0.1:{bound_port}"
    print(f"\n=======================================================")
    print(f"⚡ Submaxxing Studio Pro is live!")
    print(f"👉 Open in your browser: {url}")
    print(f"=======================================================\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")


if __name__ == "__main__":
    run_server()
