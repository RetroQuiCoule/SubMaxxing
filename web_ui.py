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
import tempfile
import threading
import webbrowser
from typing import Optional
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
PREVIEW_FILE = os.path.join(tempfile.gettempdir(), "submaxxing_web_preview.mp4")
REFRAME_PREVIEW_FILE = os.path.join(tempfile.gettempdir(), "submaxxing_reframe_preview.mp4")

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

        .nav-center {
            display: flex;
            align-items: center;
            background: #090d15;
            padding: 4px;
            border-radius: 12px;
            box-shadow: var(--neu-inset);
            border: 1px solid var(--border);
            gap: 4px;
        }
        .view-nav-btn {
            background: none;
            border: none;
            color: var(--text-dim);
            padding: 6px 14px;
            font-size: 0.8rem;
            font-weight: 700;
            border-radius: 8px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 6px;
        }
        .view-nav-btn:hover {
            color: var(--text);
        }
        .view-nav-btn.active {
            background: var(--surface-raised);
            color: #fff;
            box-shadow: 0 2px 8px rgba(0,0,0,0.4);
            border: 1px solid var(--border-highlight);
        }

        /* Smart Cut & Topics */
        .topic-item {
            background: var(--surface-raised);
            border: 1px solid var(--border);
            border-radius: 10px;
            padding: 12px;
            cursor: pointer;
            transition: all 0.2s;
        }
        .topic-item:hover {
            border-color: var(--border-highlight);
            background: rgba(255, 255, 255, 0.02);
        }
        .topic-item.selected {
            border-color: var(--accent);
            box-shadow: 0 0 12px rgba(0, 242, 254, 0.2);
            background: rgba(0, 242, 254, 0.05);
        }
        .cut-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            background: var(--surface-raised);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 8px 12px;
            font-size: 0.82rem;
            transition: all 0.2s;
        }
        .cut-item.disabled {
            opacity: 0.4;
            text-decoration: line-through;
        }
        .badge-score {
            background: var(--accent);
            color: #080d17;
            font-weight: 800;
            font-size: 0.72rem;
            padding: 2px 7px;
            border-radius: 5px;
        }
        .badge-cut {
            font-size: 0.7rem;
            padding: 2px 6px;
            border-radius: 4px;
            font-weight: 600;
            text-transform: uppercase;
        }
        .badge-cut-silence { background: rgba(148, 163, 184, 0.15); color: #94a3b8; }
        .badge-cut-filler { background: rgba(255, 0, 127, 0.15); color: #ff007f; }
        .badge-cut-stutter { background: rgba(255, 230, 0, 0.15); color: #ffe600; }
        .badge-cut-mixed { background: rgba(168, 85, 247, 0.15); color: #a855f7; }
        .badge-cut-trim { background: rgba(0, 242, 254, 0.15); color: #00f2fe; }

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

        .path-input {
            width: 100%;
            padding: 8px 12px;
            background: #090d15;
            border: 1px solid var(--border);
            border-radius: 8px;
            color: #fff;
            font-size: 0.82rem;
            font-family: Consolas, monospace;
            box-shadow: var(--neu-inset);
            outline: none;
            box-sizing: border-box;
            transition: border-color 0.2s ease;
        }
        .path-input:focus {
            border-color: var(--accent);
        }
        .pipeline-notice {
            margin-top: 8px;
            padding: 8px 12px;
            background: rgba(0, 242, 254, 0.08);
            border: 1px solid rgba(0, 242, 254, 0.25);
            border-radius: 8px;
            font-size: 0.8rem;
            color: var(--accent);
        }
        .btn-pipeline {
            border-color: rgba(0, 242, 254, 0.4);
            background: rgba(0, 242, 254, 0.1);
            color: #fff;
        }
        .btn-pipeline:hover {
            border-color: var(--accent);
            background: rgba(0, 242, 254, 0.2);
            color: #fff;
        }
        .dropzone-active {
            border-color: var(--accent) !important;
            box-shadow: 0 0 12px rgba(0, 242, 254, 0.3) !important;
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
            transition: background 0.15s ease;
        }
        .mode-badge-header {
            font-size: 0.72rem;
            font-weight: 700;
            padding: 4px 10px;
            border-radius: 20px;
            background: rgba(168, 85, 247, 0.15);
            color: #d8b4fe;
            border: 1px solid rgba(168, 85, 247, 0.4);
            letter-spacing: 0.3px;
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

        /* Animated Progress Bars */
        .progress-wrap {
            margin-top: 14px;
            background: #090d15;
            padding: 12px 16px;
            border-radius: 12px;
            border: 1px solid var(--border-highlight);
            box-shadow: var(--neu-inset);
            animation: fadeIn 0.3s ease;
        }
        .progress-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-size: 0.82rem;
            font-weight: 700;
            margin-bottom: 8px;
            color: var(--text-dim);
        }
        .progress-pct {
            font-family: Consolas, monospace;
            font-weight: 800;
            color: var(--accent);
        }
        .progress-track {
            width: 100%;
            height: 10px;
            background: rgba(255, 255, 255, 0.06);
            border-radius: 6px;
            overflow: hidden;
            position: relative;
        }
        .progress-fill {
            height: 100%;
            width: 0%;
            border-radius: 6px;
            transition: width 0.35s ease;
            background-size: 30px 30px;
            background-image: linear-gradient(
                45deg,
                rgba(255, 255, 255, 0.22) 25%,
                transparent 25%,
                transparent 50%,
                rgba(255, 255, 255, 0.22) 50%,
                rgba(255, 255, 255, 0.22) 75%,
                transparent 75%,
                transparent
            );
            animation: progressStripes 1s linear infinite;
        }
        .progress-fill-cyan {
            background-color: #00f2fe;
            box-shadow: 0 0 12px rgba(0, 242, 254, 0.6);
        }
        .progress-fill-purple {
            background-color: #a855f7;
            box-shadow: 0 0 12px rgba(168, 85, 247, 0.6);
        }
        @keyframes progressStripes {
            0% { background-position: 0 0; }
            100% { background-position: 30px 0; }
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
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .btn-submit:hover:not(:disabled) {
            transform: translateY(-2px);
            box-shadow: 0 8px 25px rgba(0, 242, 254, 0.45);
        }
        .btn-submit:disabled {
            cursor: wait;
            opacity: 0.95;
        }

        .btn-reframe-submit {
            background: var(--reframe-grad);
            box-shadow: 0 6px 20px rgba(168, 85, 247, 0.4);
            color: #fff;
        }

        .btn-progress-fill {
            position: absolute;
            top: 0; left: 0;
            height: 100%;
            width: 0%;
            background: rgba(255, 255, 255, 0.35);
            pointer-events: none;
            transition: width 0.2s ease-out;
            z-index: 1;
        }
        .btn-reframe-submit .btn-progress-fill {
            background: rgba(255, 255, 255, 0.28);
        }
        .btn-text-content {
            position: relative;
            z-index: 2;
            display: flex;
            align-items: center;
            justify-content: center;
            gap: 8px;
            width: 100%;
            pointer-events: none;
        }

        .export-options-box {
            margin-top: 14px;
            margin-bottom: 14px;
            padding: 12px 14px;
            background: rgba(255, 255, 255, 0.03);
            border: 1px solid var(--border);
            border-radius: 10px;
            display: flex;
            flex-direction: column;
            gap: 10px;
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
    <!-- Hardware SVG Convolve Sharpness Filter -->
    <svg style="position: absolute; width: 0; height: 0; pointer-events: none;">
        <defs>
            <filter id="reframeSharpnessFilter">
                <feConvolveMatrix id="sharpnessKernel" order="3" preserveAlpha="true" kernelMatrix="0 0 0 0 1 0 0 0 0"/>
            </filter>
        </defs>
    </svg>

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

        <div class="nav-center">
            <button type="button" class="view-nav-btn active" id="btnNavSubs" onclick="switchView('subtitles')">
                <span data-i18n="navSubtitles">Sous-titres</span>
            </button>
            <button type="button" class="view-nav-btn" id="btnNavSmartCut" onclick="switchView('smartcut')">
                <span data-i18n="navSmartCut">AutoCut & Thèmes</span>
            </button>
            <button type="button" class="view-nav-btn" id="btnNavReframe" onclick="switchView('reframe')">
                <span data-i18n="navReframe">Reframe 9:16</span>
            </button>
        </div>

        <div class="nav-right">
            <button type="button" class="btn-pill" id="navBackBtn" style="display:none;" onclick="switchView('subtitles')">
                <span data-i18n="backToSubs">Back to Subtitles</span>
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
                        <div class="card-title" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
                            <div class="card-title-left" data-i18n="section1Title">1. Video & Subtitles</div>
                            <div id="cacheControlWrap" style="display:inline-flex; align-items:center; gap:8px; font-size:0.75rem;">
                                <span id="cacheBadge" style="background:rgba(255,255,255,0.06); padding:4px 9px; border-radius:6px; color:var(--text-dim); border:1px solid var(--border); font-family:Consolas, monospace;">
                                    <span id="cacheInfoText">Cache: ...</span>
                                </span>
                                <button type="button" class="btn-pill" onclick="clearAppCache()" style="padding:4px 10px; font-size:0.74rem; border-radius:6px; cursor:pointer;" data-i18n="clearCacheBtn">
                                    Clear Cache
                                </button>
                            </div>
                        </div>

                        <!-- Video Selection + Pipeline triggers -->
                        <div class="form-group" id="subsVideoBox">
                            <label data-i18n="videoLabel">Vidéo (MP4 / MOV) :</label>
                            <div class="file-control-row">
                                <button type="button" class="btn-pill" onclick="browseFile('video')">
                                    <span data-i18n="browseVideo">Parcourir Vidéo...</span>
                                </button>
                                <button type="button" class="btn-reframe-trigger" onclick="openReframeView()">
                                    <span data-i18n="reframeBtn">Reframe 9:16</span>
                                </button>
                                <button type="button" class="btn-pill" onclick="switchView('smartcut')" style="font-size:0.78rem;">
                                    <span>AutoCut & Thèmes</span>
                                </button>
                                <div class="file-badge" id="videoBadge" data-i18n="noVideoSelected">Aucune vidéo sélectionnée</div>
                            </div>
                            <div style="margin-top:8px;">
                                <input type="text" id="videoPath" class="path-input" placeholder="Chemin du fichier vidéo (ex: C:/Videos/clip.mp4) ou coller ici..." oninput="setGlobalVideo(this.value, 'subtitles')">
                            </div>
                            <div id="subtitlesPipelineNotice" class="pipeline-notice" style="display:none;"></div>
                        </div>

                        <div class="form-group" style="margin-top:16px;">
                            <label class="toggle-container">
                                <input type="checkbox" id="autoTranscribe" checked>
                                <span data-i18n="transcribeCheckbox"><b>Transcribe with Local Whisper</b> (large-v3-turbo on RTX GPU)</span>
                            </label>
                        </div>

                        <!-- SRT Selection -->
                        <div class="form-group" id="srtGroup" style="display: none;">
                            <label data-i18n="srtLabel">Existing SRT Subtitles (e.g. Buzz Whisper):</label>
                            <div class="file-control-row">
                                <button type="button" class="btn-pill" onclick="browseFile('srt')">
                                    <span data-i18n="browseSrt">Browse SRT...</span>
                                </button>
                                <div class="file-badge" id="srtBadge" data-i18n="noSrtSelected">No SRT selected</div>
                            </div>
                            <div style="margin-top:8px;">
                                <input type="text" id="srtPath" class="path-input" placeholder="Chemin du fichier SRT (optionnel)..." oninput="onSrtPathChanged(this.value)">
                            </div>
                        </div>

                        <div class="row" id="whisperGroup">
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
                            <div class="card-title-left" data-i18n="section2Title">2. Style Preset & Pacing</div>
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
                            <span data-i18n="advancedTitle">ADVANCED MODE (Full Customization)</span>
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

                    <!-- 3. Export -->
                    <div class="card">
                        <div class="card-title">
                            <div class="card-title-left" data-i18n="section3Title">3. Render & Export</div>
                        </div>

                        <div class="form-group">
                            <label data-i18n="renderFormatLabel">Export Format:</label>
                            <select id="renderType">
                                <option value="burn" selected data-i18n="optBurn">Burned Video (Full MP4 with embedded subtitles via RTX GPU)</option>
                                <option value="overlay_mov" data-i18n="optProres">Transparent ProRes 4444 Overlay (.MOV for CapCut / Premiere)</option>
                                <option value="overlay_webm" data-i18n="optWebm">Transparent WebM Overlay (.webm)</option>
                                <option value="both" data-i18n="optBoth">Both (Burned MP4 + Transparent ProRes)</option>
                            </select>
                        </div>

                        <div class="export-options-box">
                            <label class="toggle-container" style="font-size: 0.85rem; font-weight: 500; cursor: pointer;">
                                <input type="checkbox" id="compressVideo" checked>
                                <span data-i18n="compressVideoLabel"><b>Smart Video Compression</b> (TikTok / Web optimized, Faststart, AAC)</span>
                            </label>
                            <label class="toggle-container" style="font-size: 0.85rem; font-weight: 500; cursor: pointer;">
                                <input type="checkbox" id="exportSubFiles">
                                <span data-i18n="exportSubFilesLabel">Also export subtitle files (.srt & .ass)</span>
                            </label>
                            <label class="toggle-container" id="keepRawReframedGroup" style="font-size: 0.85rem; font-weight: 500; cursor: pointer; display: none;">
                                <input type="checkbox" id="keepRawReframed">
                                <span data-i18n="keepRawReframedLabel">Keep raw 9:16 video (without subtitles)</span>
                            </label>
                            <label class="toggle-container" style="font-size: 0.85rem; font-weight: 500; cursor: pointer;">
                                <input type="checkbox" id="chkNormalizeAudio" checked>
                                <span data-i18n="normalizeAudioLabel"><b>Égaliser le son à 0 dB Clean</b> (Normalisation EBU R128 anti-saturation)</span>
                            </label>
                        </div>

                        <button type="submit" class="btn-submit" id="btnSubmit">
                            <div class="btn-progress-fill" id="mainBtnProgressFill"></div>
                            <span class="btn-text-content" id="mainBtnText" data-i18n="btnSubmit">GENERATE COMPLETE RENDER</span>
                        </button>

                        <div class="progress-wrap" id="mainProgressWrap" style="display:none;">
                            <div class="progress-header">
                                <span class="progress-label" id="mainProgressLabel">Processing video...</span>
                                <span class="progress-pct" id="mainProgressPct">0%</span>
                            </div>
                            <div class="progress-track">
                                <div class="progress-fill progress-fill-cyan" id="mainProgressBar" style="width: 0%;"></div>
                            </div>
                        </div>
                    </div>
                </form>

                <div id="statusBox"></div>
            </div>

            <!-- Right: TikTok Preview -->
            <div class="preview-col preview-sticky">
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left" data-i18n="previewTitle">9:16 TikTok Preview</div>
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
                        <b data-i18n="btnPreview">Preview On My Video (3s Clip)</b>
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
                            <span data-i18n="reframeTitle">Reframe Studio (16:9 → 9:16)</span>
                        </div>
                    </div>

                    <div class="form-group" id="reframeVideoBox">
                        <label data-i18n="sourceVideoLabel">Source 16:9 Video:</label>
                        <div class="file-control-row">
                            <button type="button" class="btn-pill" onclick="browseFile('reframe_video')">
                                <span data-i18n="browseVideo">Browse Video...</span>
                            </button>
                            <button type="button" class="btn-pill" onclick="switchView('smartcut')" style="font-size:0.78rem;">
                                <span>AutoCut & Thèmes</span>
                            </button>
                            <button type="button" class="btn-pill" onclick="switchView('subtitles')" style="font-size:0.78rem;">
                                <span>Sous-titres</span>
                            </button>
                            <div class="file-badge" id="reframeVideoBadge" data-i18n="noVideoSelected">No video selected</div>
                        </div>
                        <div style="margin-top:8px;">
                            <input type="text" id="reframeVideoPath" class="path-input" placeholder="Chemin du fichier 16:9 ou coller ici..." oninput="setGlobalVideo(this.value, 'reframe')">
                        </div>
                        <div id="reframePipelineNotice" class="pipeline-notice" style="display:none;"></div>
                    </div>

                    <div class="form-group" style="margin-top:16px;">
                        <label data-i18n="framingModeLabel">Framing Mode:</label>
                        <select id="reframeMode" onchange="updateReframePreview()">
                            <option value="face_track" selected data-i18n="optFaceTrack">Auto Face Tracking (Smart Pan on Speaker)</option>
                            <option value="split_screen" data-i18n="optSplitScreen">Podcast / Split-Screen (Stacked Top & Bottom)</option>
                            <option value="blurred_bg" data-i18n="optBlurredBg">Blurred Background (16:9 Center + Blown Blur)</option>
                            <option value="center" data-i18n="optCenterCrop">Fixed Center Crop</option>
                            <option value="manual" data-i18n="optManualPan">Manual Pan Slider</option>
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
                            <span data-i18n="gradingTitle">Video Grading & Enhancements</span>
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
                    <div style="margin-bottom:12px;">
                        <label class="toggle-container" style="font-size:0.85rem; font-weight:500; cursor:pointer;">
                            <input type="checkbox" id="chkReframeNormalizeAudio" checked>
                            <span><b>Égaliser le son à 0 dB Clean</b> (Normalisation EBU R128 anti-saturation)</span>
                        </label>
                    </div>

                    <button type="button" class="btn-submit btn-reframe-submit" id="btnApplyReframe" onclick="applyAndReturnToSubtitles()">
                        <div class="btn-progress-fill" id="reframeBtnProgressFill"></div>
                        <span class="btn-text-content" id="reframeBtnText"><span data-i18n="btnApplyReframe">Apply Reframe & Return To Subtitles</span></span>
                    </button>

                    <div style="margin-top: 10px;">
                        <button type="button" class="btn-pill" id="btnExportReframeOnly" onclick="exportReframeOnly()" style="width: 100%; justify-content: center; padding: 11px 14px; font-weight: 700; border-color: rgba(168, 85, 247, 0.4);">
                            <span data-i18n="btnExportReframeOnly">Export 9:16 Video Only (Without Subtitles)</span>
                        </button>
                    </div>

                    <div class="progress-wrap" id="reframeProgressWrap" style="display:none;">
                        <div class="progress-header">
                            <span class="progress-label" id="reframeProgressLabel">Reframing with GPU NVENC...</span>
                            <span class="progress-pct" id="reframeProgressPct">0%</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill progress-fill-purple" id="reframeProgressBar" style="width: 0%;"></div>
                        </div>
                    </div>
                </div>

                <div id="reframeStatusBox" style="display:none;" class="card"></div>
            </div>

            <!-- Right: Reframe 9:16 Video Player -->
            <div class="preview-col preview-sticky">
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left" data-i18n="reframePreviewTitle">9:16 Reframed Output Preview</div>
                        <div id="reframeModeBadge" class="mode-badge-header">Smart Face Track</div>
                    </div>

                    <div class="phone-wrapper" id="reframePhoneWrapper">
                        <video id="reframePlayer" class="reframe-phone-video" controls autoplay loop playsinline></video>
                        <div id="reframeVignetteOverlay" class="reframe-vignette-overlay"></div>
                        <div id="reframePlaceholder" class="reframe-placeholder">
                            <div class="reframe-ph-icon" style="font-size:2.5rem; opacity:0.6;">▶</div>
                            <div class="reframe-ph-title" data-i18n="reframePlaceholderTitle">9:16 Canvas Ready</div>
                            <div class="reframe-ph-desc" data-i18n="reframePlaceholderText">Select a video to inspect framing & color grading.</div>
                        </div>
                    </div>

                    <button type="button" class="btn-preview" id="btnTestReframePreview" onclick="generateReframe3sPreview()">
                        <b data-i18n="btnPreviewReframe">Preview Reframed Clip (3s)</b>
                    </button>
                    <p style="font-size:0.75rem; color:var(--text-dim); text-align:center;" data-i18n="previewReframeDesc">
                        Fast GPU render with face tracking & color grading in ~0.5s.
                    </p>
                </div>
            </div>
        </div>
    </div>

    <!-- ================= VIEW 3: SMART CUT & THEMES STUDIO ================= -->
    <div id="viewSmartCut" class="view-section">
        <div class="main-layout">
            <div class="controls-col">
                <!-- 1. Source & Settings -->
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left">1. Analyse & Découpage Intelligent</div>
                    </div>
                    <div class="form-group" id="smartCutVideoBox">
                        <label>Vidéo Source (Interview, Podcast, Débat) :</label>
                        <div class="file-control-row">
                            <button type="button" class="btn-pill" onclick="browseSmartCutVideo()">
                                <span data-i18n="browseVideo">Parcourir Vidéo...</span>
                            </button>
                            <button type="button" class="btn-pill" onclick="switchView('reframe')" style="font-size:0.78rem;">
                                <span>Reframe 9:16</span>
                            </button>
                            <button type="button" class="btn-pill" onclick="switchView('subtitles')" style="font-size:0.78rem;">
                                <span>Sous-titres</span>
                            </button>
                            <div class="file-badge" id="smartCutVideoBadge">Aucune vidéo sélectionnée</div>
                        </div>
                        <div style="margin-top:8px;">
                            <input type="text" id="smartCutVideoPath" class="path-input" placeholder="Chemin de la vidéo 16:9 ou coller ici..." oninput="setGlobalVideo(this.value, 'smartcut')">
                        </div>
                        <div id="smartCutPipelineNotice" class="pipeline-notice" style="display:none;"></div>
                    </div>

                    <div class="row" style="margin-top:14px;">
                        <div class="form-group">
                            <label>Seuil de Silence (<span id="silenceThreshVal">0.50</span>s) :</label>
                            <div class="slider-group">
                                <input type="range" id="silenceThreshSlider" min="0.2" max="1.5" step="0.05" value="0.5" oninput="document.getElementById('silenceThreshVal').innerText = parseFloat(this.value).toFixed(2); document.getElementById('silenceThreshValDisplay').innerText = parseFloat(this.value).toFixed(2) + 's';">
                                <span class="slider-val" id="silenceThreshValDisplay">0.50s</span>
                            </div>
                        </div>
                        <div class="form-group">
                            <label>Moteur de Découpage :</label>
                            <select id="smartCutEngine">
                                <option value="heuristic" selected>Analyse Sémantique Locale (Instantané)</option>
                                <option value="llm">Micro-LLM Local (Ollama / GGUF)</option>
                            </select>
                        </div>
                    </div>

                    <div style="display:flex; flex-direction:column; gap:8px; margin-top:8px;">
                        <label class="toggle-container" style="font-size:0.85rem; cursor:pointer;">
                            <input type="checkbox" id="chkDetectStutters" checked>
                            <span>Supprimer les bégaiements et répétitions immédiates</span>
                        </label>
                        <label class="toggle-container" style="font-size:0.85rem; cursor:pointer;">
                            <input type="checkbox" id="chkDetectFillers" checked>
                            <span>Supprimer les tics de langage et hésitations (euh, bah, genre...)</span>
                        </label>
                    </div>

                    <div id="smartCutLlmOptions" style="display:none; margin-top:14px; padding:12px; background:var(--surface-raised); border-radius:10px; border:1px solid var(--border);">
                        <div class="form-group" style="margin-bottom:8px;">
                            <label style="font-size:0.75rem;">URL Endpoint Ollama :</label>
                            <input type="text" id="smartCutLlmUrl" value="http://localhost:11434/v1" class="text-input" style="width:100%; font-size:0.8rem; padding:6px 10px; background:#0d111a; border:1px solid var(--border); color:#fff; border-radius:6px;">
                        </div>
                        <div class="form-group" style="margin-bottom:0;">
                            <label style="font-size:0.75rem;">Modèle Ollama :</label>
                            <input type="text" id="smartCutLlmModel" value="llama3.2:3b" class="text-input" style="width:100%; font-size:0.8rem; padding:6px 10px; background:#0d111a; border:1px solid var(--border); color:#fff; border-radius:6px;">
                        </div>
                    </div>

                    <button type="button" class="btn-submit" id="btnRunSmartCutAnalysis" onclick="runSmartCutAnalysis()" style="margin-top:16px;">
                        <span class="btn-text-content">Analyser la vidéo (Détection thèmes & jumpcuts)</span>
                    </button>

                    <div class="progress-wrap" id="smartCutProgressWrap" style="display:none;">
                        <div class="progress-header">
                            <span class="progress-label" id="smartCutProgressLabel">Transcription Whisper & Analyse...</span>
                            <span class="progress-pct" id="smartCutProgressPct">0%</span>
                        </div>
                        <div class="progress-track">
                            <div class="progress-fill progress-fill-cyan" id="smartCutProgressBar" style="width: 0%;"></div>
                        </div>
                    </div>
                </div>

                <!-- 2. Thematic Chapters (Moments Pertinents) -->
                <div class="card" id="cardTopics" style="display:none;">
                    <div class="card-title">
                        <div class="card-title-left">2. Thèmes & Extraits Détectés</div>
                        <span id="topicsCountBadge" class="brand-badge">0 extraits</span>
                    </div>
                    <p style="font-size:0.8rem; color:var(--text-dim); margin-bottom:12px;">
                        Cliquez sur un extrait pour l'isoler au montage (format Short/Reel), ou gardez la vidéo entière.
                    </p>
                    <div id="topicsContainer" style="display:flex; flex-direction:column; gap:10px; max-height:280px; overflow-y:auto; padding-right:4px;">
                        <!-- Injected dynamically -->
                    </div>
                </div>

                <!-- 3. Jump-Cuts Review Table -->
                <div class="card" id="cardCuts" style="display:none;">
                    <div class="card-title">
                        <div class="card-title-left">3. Coupes Proposées (Jump-Cuts à valider)</div>
                        <div style="display:flex; gap:8px;">
                            <button type="button" class="btn-pill" onclick="toggleAllCuts(true)" style="padding:4px 10px; font-size:0.75rem;">Tout activer</button>
                            <button type="button" class="btn-pill" onclick="toggleAllCuts(false)" style="padding:4px 10px; font-size:0.75rem;">Tout désactiver</button>
                        </div>
                    </div>
                    <div id="cutsSummaryBar" style="font-size:0.85rem; color:var(--accent); margin-bottom:10px; font-weight:600;"></div>
                    <div id="cutsContainer" style="display:flex; flex-direction:column; gap:6px; max-height:260px; overflow-y:auto; padding-right:4px;">
                        <!-- Injected dynamically -->
                    </div>
                </div>

                <!-- 4. Render Action -->
                <div class="card" id="cardRenderSmartCut" style="display:none;">
                    <div class="card-title">
                        <div class="card-title-left">4. Export & Rendu Dynamisé</div>
                    </div>

                    <div style="display:flex; align-items:center; justify-content:space-between; margin-bottom:14px; flex-wrap:wrap; gap:10px;">
                        <label class="toggle-container" style="font-size:0.85rem; cursor:pointer;">
                            <input type="checkbox" id="chkSmartCutSubtitles" checked>
                            <span>Incruster les sous-titres animés synchronisés</span>
                        </label>
                        <select id="smartCutPreset" style="width:160px; font-size:0.8rem;">
                            <option value="hormozi" selected>Hormozi</option>
                            <option value="mrbeast">MrBeast</option>
                            <option value="neon_glow">Neon Glow</option>
                            <option value="clean_minimal">Clean Minimal</option>
                            <option value="tiktok_bold">TikTok Bold</option>
                        </select>
                    </div>

                    <div style="margin-bottom:14px;">
                        <label class="toggle-container" style="font-size:0.85rem; font-weight:500; cursor:pointer;">
                            <input type="checkbox" id="chkSmartCutNormalizeAudio" checked>
                            <span><b>Égaliser le son à 0 dB Clean</b> (Anti-saturation / Voix claire)</span>
                        </label>
                    </div>

                    <button type="button" class="btn-submit" id="btnRenderSmartCut" onclick="renderSmartCutVideo()">
                        <span class="btn-text-content">Générer la Vidéo Dynamisée (Jumpcuts)</span>
                    </button>

                    <div id="smartCutStatusBox" style="display:none; margin-top:12px;" class="card"></div>
                </div>
            </div>

            <!-- Right: Preview & Stats Player -->
            <div class="preview-col preview-sticky">
                <div class="card">
                    <div class="card-title">
                        <div class="card-title-left">Lecteur & Prévisualisation</div>
                    </div>
                    <div class="phone-wrapper">
                        <video id="smartCutPlayer" class="reframe-phone-video" controls playsinline></video>
                        <div id="smartCutPlaceholder" class="reframe-placeholder">
                            <div class="reframe-ph-icon" style="font-size:2.5rem; opacity:0.6;">▶</div>
                            <div class="reframe-ph-title">Lecteur Prêt</div>
                            <div class="reframe-ph-desc">Sélectionnez une vidéo pour analyser les thèmes et les coupes.</div>
                        </div>
                    </div>

                    <div id="smartCutStatsPanel" style="display:none; margin-top:14px; padding:12px; background:var(--surface-raised); border-radius:10px; font-size:0.85rem; border:1px solid var(--border);">
                        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                            <span style="color:var(--text-dim);">Durée sélectionnée :</span>
                            <span id="statOrigDur" style="font-weight:700;">-</span>
                        </div>
                        <div style="display:flex; justify-content:space-between; margin-bottom:6px;">
                            <span style="color:var(--text-dim);">Temps supprimé :</span>
                            <span id="statCutDur" style="color:var(--pink); font-weight:700;">-</span>
                        </div>
                        <div style="display:flex; justify-content:space-between;">
                            <span style="color:var(--text-dim);">Durée finale estimée :</span>
                            <span id="statNewDur" style="color:var(--accent); font-weight:700;">-</span>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>

    <script>
        // Bilingual Dictionary
        const I18N = {
            en: {
                navSubtitles: "Subtitles",
                navSmartCut: "AutoCut & Topics",
                navReframe: "Reframe 9:16",
                section1Title: "1. Video & Subtitles",
                videoLabel: "9:16 Video (MP4 / MOV):",
                browseVideo: "Browse Video...",
                reframeBtn: "Reframe",
                noVideoSelected: "No video selected",
                transcribeCheckbox: "<b>Transcribe with Local Whisper</b> (large-v3-turbo on RTX GPU)",
                srtLabel: "Existing SRT Subtitles (e.g. Buzz Whisper):",
                browseSrt: "Browse SRT...",
                noSrtSelected: "No SRT selected",
                langLabel: "Audio Language:",
                modelLabel: "Whisper Model:",
                section2Title: "2. Style Preset & Pacing",
                presetLabel: "Style Preset:",
                wordsPerChunkLabel: "Words Per Screen:",
                animationLabel: "Animation:",
                verticalPosLabel: "Vertical Position (Height):",
                advancedTitle: "ADVANCED MODE (Full Customization)",
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
                section3Title: "3. Render & Export",
                renderFormatLabel: "Export Format:",
                optBurn: "Burned Video (Full MP4 with embedded subtitles via RTX GPU)",
                optProres: "Transparent ProRes 4444 Overlay (.MOV for CapCut / Premiere)",
                optWebm: "Transparent WebM Overlay (.webm)",
                optBoth: "Both (Burned MP4 + Transparent ProRes)",
                btnSubmit: "GENERATE COMPLETE RENDER",
                previewTitle: "9:16 TikTok Preview",
                safeZoneToggle: "Safe Zone Guide",
                safeZoneLabel: "SUBTITLES SAFE ZONE",
                btnPreview: "Preview On My Video (3s Clip)",
                previewDesc: "Renders the first 3 seconds of your actual video with RTX GPU in ~0.5s.",
                backToSubs: "Back to Subtitles",
                reframeTitle: "Reframe Studio (16:9 → 9:16)",
                sourceVideoLabel: "Source 16:9 Video:",
                framingModeLabel: "Framing Mode:",
                optFaceTrack: "Auto Face Tracking (Smart Pan on Speaker)",
                optSplitScreen: "Podcast / Split-Screen (Stacked Top & Bottom)",
                optBlurredBg: "Blurred Background (16:9 Center + Blown Blur)",
                optCenterCrop: "Fixed Center Crop",
                optManualPan: "Manual Pan Slider",
                manualPanLabel: "Manual Camera Pan (Left → Right):",
                gradingTitle: "Video Grading & Enhancements",
                sharpnessLabel: "Sharpness (Nettoyage):",
                contrastLabel: "Contrast:",
                saturationLabel: "Saturation (Vibrant):",
                brightnessLabel: "Brightness:",
                vignetteLabel: "Vignette (Focus border):",
                btnApplyReframe: "Apply Reframe & Return To Subtitles",
                btnExportReframeOnly: "Export 9:16 Video Only (Without Subtitles)",
                exportSubFilesLabel: "Also export subtitle files (.srt & .ass)",
                keepRawReframedLabel: "Keep intermediate raw 9:16 video (without subtitles)",
                reframeExportSuccess: "Reframed 9:16 video saved to: ",
                reframePreviewTitle: "9:16 Reframed Output Preview",
                reframePlaceholderTitle: "9:16 Canvas Ready",
                reframePlaceholderText: "Select a video and click Preview Reframed Clip to inspect AI framing & adjustments.",
                btnPreviewReframe: "Preview Reframed Clip (3s)",
                previewReframeDesc: "Fast GPU render with face tracking & color grading in ~0.5s.",
                statusStart: "[*] Processing started locally...",
                successMsg: "SUCCESS!",
                errorMsg: "ERROR:",
                openFolderBtn: "Open File Location",
                clearCacheBtn: "Clear Cache",
                cacheClearedMsg: "Cache cleared successfully!",
                compressVideoLabel: "<b>Smart Video Compression</b> (TikTok / Web optimized, Faststart, AAC)",
                normalizeAudioLabel: "<b>Clean 0 dB Audio Normalization</b> (EBU R128 broadcast anti-clipping)"
            },
            fr: {
                navSubtitles: "Sous-titres",
                navSmartCut: "AutoCut & Thèmes",
                navReframe: "Reframe 9:16",
                section1Title: "1. Vidéo & Sous-titres",
                videoLabel: "Vidéo 9:16 (MP4 / MOV) :",
                browseVideo: "Parcourir Vidéo...",
                reframeBtn: "Reframe",
                noVideoSelected: "Aucune vidéo sélectionnée",
                transcribeCheckbox: "<b>Générer avec Whisper local</b> (large-v3-turbo sur GPU RTX)",
                srtLabel: "Fichier SRT existant (ex: export Buzz Whisper) :",
                browseSrt: "Parcourir SRT...",
                noSrtSelected: "Aucun SRT sélectionné",
                langLabel: "Langue audio :",
                modelLabel: "Modèle Whisper :",
                section2Title: "2. Modèle de Style & Pacing",
                presetLabel: "Preset de Style :",
                wordsPerChunkLabel: "Mots par écran :",
                animationLabel: "Animation :",
                verticalPosLabel: "Position Verticale (Hauteur) :",
                advancedTitle: "MODE AVANCÉ (Personnalisation complète)",
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
                section3Title: "3. Rendu & Export",
                renderFormatLabel: "Format d'exportation :",
                optBurn: "Rendu complet (MP4 avec sous-titres incrustés via GPU RTX)",
                optProres: "Overlay Transparent ProRes 4444 (.MOV pour CapCut / Premiere)",
                optWebm: "Overlay Transparent WebM (.webm)",
                optBoth: "Les deux (MP4 incrusté + Overlay ProRes)",
                btnSubmit: "GÉNÉRER LE RENDU COMPLET",
                previewTitle: "Aperçu 9:16 TikTok",
                safeZoneToggle: "Guide Safe Zone",
                safeZoneLabel: "ZONE IDÉALE SOUS-TITRES",
                btnPreview: "Prévisualiser sur ma vidéo (Extrait 3s)",
                previewDesc: "Génère les 3 premières secondes de votre vraie vidéo avec GPU RTX en ~0.5s.",
                backToSubs: "Retour aux Sous-titres",
                reframeTitle: "Studio Reframe (16:9 → 9:16)",
                sourceVideoLabel: "Vidéo 16:9 Source :",
                framingModeLabel: "Mode de Cadrage :",
                optFaceTrack: "Suivi Automatique du Visage (Smart Pan)",
                optSplitScreen: "Podcast / Split-Screen (Empilement Haut / Bas)",
                optBlurredBg: "Fond Flouté (16:9 au centre + arrière-plan flou)",
                optCenterCrop: "Centré Fixe",
                optManualPan: "Balayage Manuel (Slider)",
                manualPanLabel: "Cadrage Manuel (Gauche → Droite) :",
                gradingTitle: "Ajustements & Retouches Vidéo",
                sharpnessLabel: "Netteté (Nettoyage) :",
                contrastLabel: "Contraste :",
                saturationLabel: "Saturation (Vibrant) :",
                brightnessLabel: "Luminosité :",
                vignetteLabel: "Vignettage (Assombrir bords) :",
                btnApplyReframe: "Appliquer le Reframe & Revenir aux Sous-titres",
                btnExportReframeOnly: "Exporter uniquement le 9:16 (sans sous-titres)",
                exportSubFilesLabel: "Exporter aussi les fichiers sous-titres (.srt & .ass)",
                keepRawReframedLabel: "Conserver la vidéo 9:16 brute intermédiaire (sans sous-titres)",
                reframeExportSuccess: "Vidéo 9:16 enregistrée sous : ",
                reframePreviewTitle: "Aperçu du Rendu 9:16",
                reframePlaceholderTitle: "Canevas 9:16 Prêt",
                reframePlaceholderText: "Sélectionnez une vidéo et cliquez sur « Prévisualiser l'extrait » pour inspecter le cadrage IA et les retouches.",
                btnPreviewReframe: "Prévisualiser l'extrait (3s)",
                previewReframeDesc: "Rendu GPU rapide avec détection faciale & retouches en ~0.5s.",
                statusStart: "[*] Lancement du traitement local...",
                successMsg: "SUCCÈS !",
                errorMsg: "ERREUR :",
                openFolderBtn: "Ouvrir l'emplacement du fichier",
                clearCacheBtn: "Vider le cache",
                cacheClearedMsg: "Cache vidé avec succès !",
                compressVideoLabel: "<b>Compression Vidéo Optimisée</b> (Optimisé TikTok / Web, Faststart, AAC)",
                normalizeAudioLabel: "<b>Égaliser le son à 0 dB Clean</b> (Normalisation EBU R128 anti-saturation)"
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

        function getCurrentGlobalVideo() {
            const v1 = document.getElementById('videoPath') ? document.getElementById('videoPath').value.trim() : '';
            const v2 = document.getElementById('smartCutVideoPath') ? document.getElementById('smartCutVideoPath').value.trim() : '';
            const v3 = document.getElementById('reframeVideoPath') ? document.getElementById('reframeVideoPath').value.trim() : '';
            return v1 || v2 || v3 || '';
        }

        function setGlobalVideo(fullPath, sourceModule) {
            if (!fullPath) return;
            const clean = fullPath.trim().replace(/^"(.*)"$/, '$1');
            const filename = clean.split(/[/\\\\]/).pop();

            // 1. Inputs
            const vPath = document.getElementById('videoPath');
            const scPath = document.getElementById('smartCutVideoPath');
            const rfPath = document.getElementById('reframeVideoPath');
            if (vPath) vPath.value = clean;
            if (scPath) scPath.value = clean;
            if (rfPath) rfPath.value = clean;

            // 2. Badges
            const vBadge = document.getElementById('videoBadge');
            const scBadge = document.getElementById('smartCutVideoBadge');
            const rfBadge = document.getElementById('reframeVideoBadge');
            if (vBadge) { vBadge.innerText = filename; vBadge.className = 'file-badge has-file'; }
            if (scBadge) { scBadge.innerText = filename; scBadge.className = 'file-badge has-file'; }
            if (rfBadge) { rfBadge.innerText = filename; rfBadge.className = 'file-badge has-file'; }

            // 3. SmartCut Player
            const scPlayer = document.getElementById('smartCutPlayer');
            const scPh = document.getElementById('smartCutPlaceholder');
            if (scPlayer) {
                if (scPh) scPh.style.display = 'none';
                scPlayer.style.display = 'block';
                scPlayer.src = `/api/stream_video?path=${encodeURIComponent(clean)}`;
                scPlayer.load();
            }

            // 4. Reframe Player
            const rfPlayer = document.getElementById('reframePlayer');
            const rfPh = document.getElementById('reframePlaceholder');
            if (rfPlayer) {
                if (rfPh) rfPh.style.display = 'none';
                rfPlayer.style.display = 'block';
                rfPlayer.src = `/api/stream_video?path=${encodeURIComponent(clean)}`;
                rfPlayer.load();
                rfPlayer.play().catch(() => {});
            }

            checkVideoCache(clean);
        }

        function setReframeVideo(fullPath) {
            setGlobalVideo(fullPath, 'reframe');
            updateReframePreview();
        }

        function setSmartCutVideo(fullPath) {
            setGlobalVideo(fullPath, 'smartcut');
        }

        function onSrtPathChanged(val) {
            if (!val) return;
            const clean = val.trim().replace(/^"(.*)"$/, '$1');
            const filename = clean.split(/[/\\\\]/).pop();
            const badge = document.getElementById('srtBadge');
            if (badge) {
                badge.innerText = filename;
                badge.className = 'file-badge has-file';
            }
        }

        function sendToReframe(filePath) {
            const path = filePath || getCurrentGlobalVideo();
            if (!path) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo." : "Please select a video first.");
                return;
            }
            setGlobalVideo(path, 'smartcut');
            switchView('reframe');
            const notice = document.getElementById('reframePipelineNotice');
            if (notice) {
                notice.style.display = 'block';
                notice.innerText = currentLang === 'fr'
                    ? "Vidéo transférée depuis AutoCut. Choisissez votre cadrage 9:16 puis exportez ou passez aux sous-titres."
                    : "Video received from AutoCut. Select your 9:16 framing, then export or send to subtitles.";
            }
        }

        function sendToSubtitles(filePath) {
            const path = filePath || getCurrentGlobalVideo();
            if (!path) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo." : "Please select a video first.");
                return;
            }
            setGlobalVideo(path, 'reframe');
            switchView('subtitles');
            const notice = document.getElementById('subtitlesPipelineNotice');
            if (notice) {
                notice.style.display = 'block';
                notice.innerText = currentLang === 'fr'
                    ? "Vidéo chargée dans le studio de sous-titres. Personnalisez vos sous-titres animés ci-dessous."
                    : "Video loaded in Subtitles Studio. Customize your animated subtitles below.";
            }
        }

        function sendToSmartCut(filePath) {
            const path = filePath || getCurrentGlobalVideo();
            if (!path) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo." : "Please select a video first.");
                return;
            }
            setGlobalVideo(path, 'subtitles');
            switchView('smartcut');
            const notice = document.getElementById('smartCutPipelineNotice');
            if (notice) {
                notice.style.display = 'block';
                notice.innerText = currentLang === 'fr'
                    ? "Vidéo chargée dans AutoCut. Lancez l'analyse pour détecter les thèmes et jump-cuts."
                    : "Video loaded in AutoCut. Run analysis to detect themes and jump-cuts.";
            }
        }

        // View Switcher (Subtitles <-> SmartCut <-> Reframe)
        function switchView(viewName) {
            document.getElementById('viewSubtitles').className = 'view-section' + (viewName === 'subtitles' ? ' active' : '');
            const vSmartCut = document.getElementById('viewSmartCut');
            if (vSmartCut) vSmartCut.className = 'view-section' + (viewName === 'smartcut' ? ' active' : '');
            document.getElementById('viewReframe').className = 'view-section' + (viewName === 'reframe' ? ' active' : '');

            const btnSubs = document.getElementById('btnNavSubs');
            const btnSmartCut = document.getElementById('btnNavSmartCut');
            const btnReframe = document.getElementById('btnNavReframe');
            if (btnSubs) btnSubs.className = 'view-nav-btn' + (viewName === 'subtitles' ? ' active' : '');
            if (btnSmartCut) btnSmartCut.className = 'view-nav-btn' + (viewName === 'smartcut' ? ' active' : '');
            if (btnReframe) btnReframe.className = 'view-nav-btn' + (viewName === 'reframe' ? ' active' : '');

            document.getElementById('navBackBtn').style.display = (viewName !== 'subtitles') ? 'inline-flex' : 'none';

            const currentVid = getCurrentGlobalVideo();
            const badge = document.getElementById('brandBadge');
            if (viewName === 'reframe') {
                document.body.classList.add('theme-reframe');
                if (badge) badge.innerText = 'REFRAME STUDIO';
                if (currentVid) {
                    setGlobalVideo(currentVid, 'reframe');
                }
                updateReframePreview();
            } else if (viewName === 'smartcut') {
                document.body.classList.remove('theme-reframe');
                if (badge) badge.innerText = 'SMART CUT STUDIO';
                if (currentVid) {
                    setGlobalVideo(currentVid, 'smartcut');
                }
            } else {
                document.body.classList.remove('theme-reframe');
                if (badge) badge.innerText = 'STUDIO PRO';
                if (currentVid) {
                    setGlobalVideo(currentVid, 'subtitles');
                }
                updateMockup();
            }
        }

        function openReframeView() {
            const currentVid = getCurrentGlobalVideo();
            if (currentVid) {
                setGlobalVideo(currentVid, 'reframe');
            }
            switchView('reframe');
        }

        // ================= SMART CUT & THEMES LOGIC =================
        let smartCutData = {
            video: '',
            duration: 0,
            cuts: [],
            topics: [],
            selectedTopic: null
        };

        async function browseSmartCutVideo() {
            await browseFile('video');
        }

        function toggleAllCuts(enabled) {
            smartCutData.cuts.forEach(c => c.enabled = enabled);
            renderCutsList();
            updateSmartCutStats();
        }

        function toggleCut(id) {
            const cut = smartCutData.cuts.find(c => c.id === id);
            if (cut) {
                cut.enabled = !cut.enabled;
                renderCutsList();
                updateSmartCutStats();
            }
        }

        function selectTopic(id) {
            if (smartCutData.selectedTopic && smartCutData.selectedTopic.id === id) {
                smartCutData.selectedTopic = null; // Toggle back to full
            } else {
                smartCutData.selectedTopic = smartCutData.topics.find(t => t.id === id) || null;
            }
            renderTopicsList();
            updateSmartCutStats();
            if (smartCutData.selectedTopic) {
                const player = document.getElementById('smartCutPlayer');
                if (player) {
                    player.currentTime = smartCutData.selectedTopic.start;
                    player.play().catch(() => {});
                }
            }
        }

        function updateSmartCutStats() {
            const origDur = smartCutData.duration || 0;
            let activeCuts = smartCutData.cuts.filter(c => c.enabled);

            let cutDur = 0;
            if (smartCutData.selectedTopic) {
                const t = smartCutData.selectedTopic;
                const cutsInTopic = activeCuts.filter(c => c.start >= t.start && c.end <= t.end);
                cutDur = cutsInTopic.reduce((acc, c) => acc + c.duration, 0);
                const topicOrig = t.duration;
                document.getElementById('statOrigDur').innerText = topicOrig.toFixed(1) + 's (Extrait #' + t.id + ')';
                document.getElementById('statCutDur').innerText = '-' + cutDur.toFixed(1) + 's (' + cutsInTopic.length + ' coupes)';
                document.getElementById('statNewDur').innerText = Math.max(0, topicOrig - cutDur).toFixed(1) + 's';
            } else {
                cutDur = activeCuts.reduce((acc, c) => acc + c.duration, 0);
                document.getElementById('statOrigDur').innerText = origDur.toFixed(1) + 's (Vidéo complète)';
                document.getElementById('statCutDur').innerText = '-' + cutDur.toFixed(1) + 's (' + activeCuts.length + ' coupes)';
                document.getElementById('statNewDur').innerText = Math.max(0, origDur - cutDur).toFixed(1) + 's';
            }
            document.getElementById('cutsSummaryBar').innerText = activeCuts.length + ' coupe(s) active(s) • ' + cutDur.toFixed(1) + 's supprimée(s)';
        }

        function renderTopicsList() {
            const cont = document.getElementById('topicsContainer');
            if (!smartCutData.topics || smartCutData.topics.length === 0) {
                cont.innerHTML = '<p style="color:var(--text-dim); font-size:0.8rem;">Aucun thème distinct détecté.</p>';
                return;
            }
            document.getElementById('topicsCountBadge').innerText = smartCutData.topics.length + ' extraits';

            let html = '';
            smartCutData.topics.forEach(t => {
                const isSel = smartCutData.selectedTopic && smartCutData.selectedTopic.id === t.id;
                html += `
                    <div class="topic-item ${isSel ? 'selected' : ''}" onclick="selectTopic(${t.id})">
                        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:4px;">
                            <b style="font-size:0.9rem; color:#fff;">${t.title}</b>
                            <div style="display:flex; gap:6px; align-items:center;">
                                <span class="badge-score">Score: ${t.virality_score}/10</span>
                                <span style="font-size:0.75rem; color:var(--text-dim);">${t.start.toFixed(1)}s - ${t.end.toFixed(1)}s (${t.duration.toFixed(0)}s)</span>
                            </div>
                        </div>
                        <div style="font-size:0.82rem; color:var(--accent); font-weight:600; margin-bottom:4px;">
                            « ${t.hook || 'Extrait clé'} »
                        </div>
                        <div style="font-size:0.75rem; color:var(--text-dim);">
                            ${t.summary}
                        </div>
                    </div>
                `;
            });
            cont.innerHTML = html;
        }

        function renderCutsList() {
            const cont = document.getElementById('cutsContainer');
            if (!smartCutData.cuts || smartCutData.cuts.length === 0) {
                cont.innerHTML = '<p style="color:var(--text-dim); font-size:0.8rem;">Aucun silence ou bégaiement détecté.</p>';
                return;
            }

            let html = '';
            smartCutData.cuts.forEach(c => {
                const badgeClass = 'badge-cut badge-cut-' + (c.reason || 'silence');
                html += `
                    <div class="cut-item ${c.enabled ? '' : 'disabled'}">
                        <label class="toggle-container" style="font-size:0.82rem; margin-bottom:0; cursor:pointer;" onclick="event.stopPropagation()">
                            <input type="checkbox" ${c.enabled ? 'checked' : ''} onchange="toggleCut(${c.id})">
                            <span style="font-family:Consolas, monospace;">[${c.start.toFixed(2)}s → ${c.end.toFixed(2)}s]</span>
                            <span class="${badgeClass}" style="margin-left:6px;">${c.reason}</span>
                            <span style="margin-left:8px; color:var(--text);">${c.text}</span>
                        </label>
                        <span style="font-size:0.75rem; color:var(--text-dim); font-family:Consolas, monospace;">-${c.duration.toFixed(2)}s</span>
                    </div>
                `;
            });
            cont.innerHTML = html;
        }

        async function runSmartCutAnalysis() {
            const vpath = document.getElementById('smartCutVideoPath').value;
            if (!vpath) {
                alert('Veuillez d\'abord sélectionner une vidéo.');
                return;
            }

            const minSilence = parseFloat(document.getElementById('silenceThreshSlider').value);
            const detectStutters = document.getElementById('chkDetectStutters').checked;
            const detectFillers = document.getElementById('chkDetectFillers').checked;
            const engine = document.getElementById('smartCutEngine').value;
            const llmUrl = document.getElementById('smartCutLlmUrl').value;
            const llmModel = document.getElementById('smartCutLlmModel').value;

            const btn = document.getElementById('btnRunSmartCutAnalysis');
            btn.disabled = true;
            document.getElementById('smartCutProgressWrap').style.display = 'block';
            document.getElementById('smartCutProgressBar').style.width = '35%';

            try {
                const res = await fetch('/api/smartcut/analyze', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        video: vpath,
                        minSilence: minSilence,
                        detectStutters: detectStutters,
                        detectFillers: detectFillers,
                        engine: engine,
                        llmUrl: llmUrl,
                        llmModel: llmModel
                    })
                });
                const data = await res.json();
                btn.disabled = false;
                document.getElementById('smartCutProgressBar').style.width = '100%';
                setTimeout(() => {
                    document.getElementById('smartCutProgressWrap').style.display = 'none';
                }, 500);

                if (!data.success) {
                    alert('Erreur lors de l\'analyse : ' + data.error);
                    return;
                }

                smartCutData.video = vpath;
                smartCutData.duration = data.duration;
                smartCutData.cuts = data.cuts;
                smartCutData.topics = data.topics;
                smartCutData.selectedTopic = null;

                document.getElementById('cardTopics').style.display = 'block';
                document.getElementById('cardCuts').style.display = 'block';
                document.getElementById('cardRenderSmartCut').style.display = 'block';
                document.getElementById('smartCutStatsPanel').style.display = 'block';

                renderTopicsList();
                renderCutsList();
                updateSmartCutStats();

            } catch (err) {
                btn.disabled = false;
                document.getElementById('smartCutProgressWrap').style.display = 'none';
                alert('Erreur réseau / analyse : ' + err);
            }
        }

        async function renderSmartCutVideo() {
            const vpath = smartCutData.video;
            if (!vpath) {
                alert('Aucune vidéo analysée.');
                return;
            }

            const btn = document.getElementById('btnRenderSmartCut');
            btn.disabled = true;
            const statusBox = document.getElementById('smartCutStatusBox');
            statusBox.style.display = 'block';
            statusBox.innerHTML = '<div style="color:var(--accent);">Rendu en cours avec GPU NVENC & concassage audio...</div>';

            const burnSubs = document.getElementById('chkSmartCutSubtitles').checked;
            const preset = document.getElementById('smartCutPreset').value;
            const normalizeAudio = document.getElementById('chkSmartCutNormalizeAudio') ? document.getElementById('chkSmartCutNormalizeAudio').checked : true;

            try {
                const res = await fetch('/api/smartcut/render', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        video: vpath,
                        cuts: smartCutData.cuts,
                        selectedTopic: smartCutData.selectedTopic,
                        burnSubtitles: burnSubs,
                        preset: preset,
                        normalize_audio: normalizeAudio
                    })
                });
                const data = await res.json();
                btn.disabled = false;

                if (!data.success) {
                    statusBox.innerHTML = `<div style="color:var(--pink);">Erreur de rendu : ${data.error}</div>`;
                    return;
                }

                const safePath = data.output.replace(/\\\\/g, '\\\\\\\\');
                statusBox.innerHTML = `
                    <div style="color:var(--accent); font-weight:700; margin-bottom:8px;">Vidéo générée avec succès (${(data.final_duration || 0).toFixed(1)}s)</div>
                    <div style="font-size:0.8rem; color:var(--text); word-break:break-all; margin-bottom:12px;">${data.output}</div>
                    <div style="display:flex; flex-wrap:wrap; gap:8px;">
                        <button type="button" class="btn-pill" onclick="openFileInExplorer('${safePath}')">
                            Ouvrir l'emplacement
                        </button>
                        <button type="button" class="btn-pill btn-pipeline" onclick="sendToReframe('${safePath}')" style="border-color:rgba(168,85,247,0.6); background:rgba(168,85,247,0.15);">
                            Envoyer vers Reframe (16:9 → 9:16)
                        </button>
                        <button type="button" class="btn-pill btn-pipeline" onclick="sendToSubtitles('${safePath}')" style="border-color:rgba(0,242,254,0.6); background:rgba(0,242,254,0.15);">
                            Envoyer vers Sous-titres
                        </button>
                    </div>
                `;

                // Update player with the rendered video
                const player = document.getElementById('smartCutPlayer');
                if (player) {
                    player.src = `/api/stream_video?path=${encodeURIComponent(data.output)}`;
                    player.load();
                    player.play().catch(() => {});
                }

            } catch (err) {
                btn.disabled = false;
                statusBox.innerHTML = `<div style="color:var(--pink);">Erreur réseau : ${err}</div>`;
            }
        }

        const openFileLocation = openFileInExplorer;

        // Browse Native Windows Dialog
        async function browseFile(type) {
            try {
                const targetType = (type === 'srt') ? 'srt' : 'video';
                const res = await fetch(`/api/browse?type=${targetType}`, { method: 'POST' });
                const data = await res.json();
                if (data && data.path) {
                    if (type === 'srt') {
                        document.getElementById('srtPath').value = data.path;
                        onSrtPathChanged(data.path);
                    } else {
                        setGlobalVideo(data.path, type);
                    }
                }
            } catch (err) {
                console.error("Browse error:", err);
            }
        }

        async function checkVideoCache(filePath) {
            if (!filePath) return;
            try {
                const res = await fetch(`/api/check_cache?video=${encodeURIComponent(filePath)}`);
                const data = await res.json();
                if (data.cached) {
                    const badge = document.getElementById('videoBadge');
                    if (badge && !badge.innerText.includes('Prêt en cache')) {
                        badge.innerText += ' (Prêt en cache)';
                    }
                }
            } catch (e) {}
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
            const video = getCurrentGlobalVideo();
            const srt = document.getElementById('srtPath').value.trim();
            const autoTranscribe = autoTranscribeCheck.checked;

            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo MP4." : "Please select an MP4 video first.");
                return;
            }

            const btn = document.getElementById('btnTestPreview');
            btn.disabled = true;
            btn.innerHTML = currentLang === 'fr' ? "Rendu extrait 3s (GPU RTX)..." : "Rendering 3s preview (RTX GPU)...";

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
                btn.innerHTML = `<b>${I18N[currentLang].btnPreview}</b>`;
            }
        }

        // Full Subtitles Render Submission
        document.getElementById('subForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const btnSubmit = document.getElementById('btnSubmit');
            const statusBox = document.getElementById('statusBox');

            const video = getCurrentGlobalVideo();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez d'abord sélectionner une vidéo." : "Please select a video first.");
                return;
            }

            btnSubmit.disabled = true;
            statusBox.style.display = "block";
            statusBox.innerText = I18N[currentLang].statusStart;

            const prog = trackRealtimeProgress(
                'main',
                'btnSubmit',
                'mainBtnProgressFill',
                'mainBtnText',
                'mainProgressBar',
                'mainProgressPct',
                'mainProgressLabel',
                'mainProgressWrap'
            );

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
                allCaps: document.getElementById('allCaps').checked,
                compress: document.getElementById('compressVideo') ? document.getElementById('compressVideo').checked : true,
                exportSubFiles: document.getElementById('exportSubFiles').checked,
                keepRawReframed: document.getElementById('keepRawReframed') ? document.getElementById('keepRawReframed').checked : false,
                wasReframed: !!window._wasReframedInSession,
                normalizeAudio: document.getElementById('chkNormalizeAudio') ? document.getElementById('chkNormalizeAudio').checked : true
            };

            try {
                const res = await fetch('/api/process', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await res.json();
                if (data.success) {
                    prog.complete(currentLang === 'fr' ? 'Rendu vidéo terminé avec succès !' : 'Render completed successfully!');
                    statusBox.innerHTML = `
<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px; padding-bottom:10px; border-bottom:1px solid rgba(255,255,255,0.1); flex-wrap:wrap; gap:8px;">
    <span style="font-weight:700; color:#4ade80;">${I18N[currentLang].successMsg}</span>
    <div style="display:flex; flex-wrap:wrap; gap:8px;">
        <button type="button" class="btn-pill" onclick="openFileInExplorer('${(data.outputPath || '').replace(/\\\\/g, '\\\\\\\\')}')">
            ${I18N[currentLang].openFolderBtn}
        </button>
        <button type="button" class="btn-pill btn-pipeline" onclick="sendToReframe('${(data.outputPath || '').replace(/\\\\/g, '\\\\\\\\')}')">
            Recadrer en 9:16
        </button>
        <button type="button" class="btn-pill btn-pipeline" onclick="sendToSmartCut('${(data.outputPath || '').replace(/\\\\/g, '\\\\\\\\')}')">
            Découper dans AutoCut
        </button>
    </div>
</div>
<div style="font-size:0.8rem; color:var(--text-dim); margin-bottom:10px; word-break:break-all;">
    <b>${currentLang === 'fr' ? 'Fichier exporté :' : 'Exported file:'}</b> <code>${data.outputPath || ''}</code>
</div>
<pre style="margin:0; font-family:inherit; white-space:pre-wrap; max-height:220px; overflow-y:auto; color:var(--text-muted);">${data.logs || ''}</pre>
`;
                    refreshCacheInfo();
                } else {
                    prog.error(data.error || "Failed");
                    statusBox.innerText = I18N[currentLang].errorMsg + "\\n\\n" + (data.error || "An error occurred.");
                }
            } catch (err) {
                prog.error(err.message);
                statusBox.innerText = I18N[currentLang].errorMsg + " " + err.message;
            } finally {
                btnSubmit.disabled = false;
                const origText = I18N[currentLang].btnSubmit;
                const textEl = document.getElementById('mainBtnText');
                if (textEl) textEl.innerText = origText;
            }
        });

        // ================= REAL-TIME PROGRESS CONTROLLER =================
        function trackRealtimeProgress(jobType, btnId, btnFillId, btnTextId, barFillId, pctId, lblId, wrapId) {
            const wrap = document.getElementById(wrapId);
            const barFill = document.getElementById(barFillId);
            const pct = document.getElementById(pctId);
            const lbl = document.getElementById(lblId);
            const btn = document.getElementById(btnId);
            const btnFill = document.getElementById(btnFillId);
            const btnText = document.getElementById(btnTextId);

            if (wrap) wrap.style.display = 'block';
            if (barFill) {
                barFill.style.width = '0%';
                barFill.style.backgroundColor = '';
            }
            if (btnFill) btnFill.style.width = '0%';
            if (pct) pct.innerText = '0%';
            if (lbl) lbl.innerText = currentLang === 'fr' ? 'Initialisation du traitement...' : 'Initializing processing...';

            let pollInterval = setInterval(async () => {
                try {
                    const res = await fetch('/api/progress');
                    const data = await res.json();

                    if (data && data.active && data.type === jobType) {
                        const curPct = Math.min(99, Math.max(0, Math.round(data.percent || 0)));
                        if (barFill) barFill.style.width = `${curPct}%`;
                        if (btnFill) btnFill.style.width = `${curPct}%`;
                        if (pct) pct.innerText = `${curPct}%`;

                        let desc = data.message || '';
                        let btnDesc = `${curPct}%`;

                        if (data.stage === 'whisper') {
                            desc = currentLang === 'fr'
                                ? `Whisper AI (CUDA GPU) : ${data.cur_sec}s / ${data.total_sec}s (${curPct}%)`
                                : `Whisper AI (CUDA GPU): ${data.cur_sec}s / ${data.total_sec}s (${curPct}%)`;
                            btnDesc = `Whisper ${curPct}%`;
                        } else if (data.stage === 'face_track') {
                            desc = currentLang === 'fr'
                                ? `Détection faciale & cadrage (${curPct}%)`
                                : `OpenCV Face Tracking (${curPct}%)`;
                            btnDesc = `Face Track ${curPct}%`;
                        } else if (data.stage === 'nvenc') {
                            desc = currentLang === 'fr'
                                ? `GPU NVENC : ${data.cur_sec}s / ${data.total_sec}s (${curPct}%) • ${data.speed}`
                                : `GPU NVENC: ${data.cur_sec}s / ${data.total_sec}s (${curPct}%) • ${data.speed}`;
                            btnDesc = `NVENC ${curPct}% (${data.speed})`;
                        } else if (data.stage === 'init') {
                            desc = currentLang === 'fr' ? 'Préparation du flux vidéo...' : 'Preparing video stream...';
                            btnDesc = `${curPct}%`;
                        }

                        if (lbl) lbl.innerText = desc;
                        if (btnText) btnText.innerHTML = `<b>${btnDesc}</b>`;
                    }
                } catch (e) {}
            }, 250);

            return {
                complete: (msg) => {
                    clearInterval(pollInterval);
                    if (barFill) barFill.style.width = '100%';
                    if (btnFill) btnFill.style.width = '100%';
                    if (pct) pct.innerText = '100%';
                    if (lbl) lbl.innerText = msg || (currentLang === 'fr' ? 'Traitement terminé avec succès !' : 'Completed successfully!');
                    if (btnText) btnText.innerHTML = `<b>${currentLang === 'fr' ? 'TERMINÉ (100%)' : 'DONE (100%)'}</b>`;
                    setTimeout(() => {
                        if (wrap) wrap.style.display = 'none';
                        if (barFill) barFill.style.width = '0%';
                        if (btnFill) btnFill.style.width = '0%';
                    }, 2500);
                },
                error: (errMsg) => {
                    clearInterval(pollInterval);
                    if (barFill) {
                        barFill.style.width = '100%';
                        barFill.style.backgroundColor = '#ef4444';
                    }
                    if (btnFill) btnFill.style.width = '0%';
                    if (lbl) lbl.innerText = errMsg || (currentLang === 'fr' ? 'Erreur' : 'Failed');
                    if (btnText) btnText.innerHTML = `<b>${currentLang === 'fr' ? 'ERREUR' : 'ERROR'}</b>`;
                    setTimeout(() => {
                        if (wrap) wrap.style.display = 'none';
                        if (barFill) {
                            barFill.style.width = '0%';
                            barFill.style.backgroundColor = '';
                        }
                    }, 3500);
                }
            };
        }

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

            // 1. Live Hardware SVG Convolution Sharpness Matrix
            const kernel = document.getElementById('sharpnessKernel');
            if (kernel) {
                if (sharpness > 0) {
                    const k = (sharpness / 100.0) * 0.75;
                    const center = (1.0 + 4 * k).toFixed(3);
                    const edge = (-k).toFixed(3);
                    kernel.setAttribute('kernelMatrix', `0 ${edge} 0 ${edge} ${center} ${edge} 0 ${edge} 0`);
                } else {
                    kernel.setAttribute('kernelMatrix', '0 0 0 0 1 0 0 0 0');
                }
            }

            // 2. Live CSS Color Grading & Filter on video
            const player = document.getElementById('reframePlayer');
            const cVal = 1 + (contrast / 100);
            const sVal = 1 + (saturation / 100);
            const bVal = 1 + (brightness / 100);
            player.style.filter = `contrast(${cVal}) saturate(${sVal}) brightness(${bVal}) url(#reframeSharpnessFilter)`;

            // 3. Framing Object-Position (Manual Pan & Center)
            if (mode === 'manual') {
                const panPct = parseInt(document.getElementById('manualPan').value);
                player.style.objectPosition = `${panPct}% center`;
            } else if (mode === 'center') {
                player.style.objectPosition = '50% center';
            } else {
                player.style.objectPosition = 'center center';
            }

            // 4. Subtle Cinema Radial Vignette (Matches FFmpeg Calibrated Curve)
            const vigOverlay = document.getElementById('reframeVignetteOverlay');
            if (vigOverlay) {
                if (vignette > 0) {
                    const vRatio = vignette / 100.0;
                    const darkness = (0.2 + vRatio * 0.75).toFixed(2);
                    const innerRadius = Math.round(72 - vRatio * 35);
                    vigOverlay.style.background = `radial-gradient(ellipse at center, transparent ${innerRadius}%, rgba(0,0,0,${darkness}) 100%)`;
                } else {
                    vigOverlay.style.background = 'none';
                }
            }

            // 5. Update Mode Badge text in header
            const modeBadge = document.getElementById('reframeModeBadge');
            const modeNames = {
                face_track: 'Smart Face Track',
                split_screen: 'Podcast Split-Screen',
                blurred_bg: 'Blurred Background',
                center: 'Fixed Center',
                manual: 'Manual Pan'
            };
            if (modeBadge) modeBadge.innerText = modeNames[mode] || mode;
        }

        async function generateReframe3sPreview() {
            const video = getCurrentGlobalVideo();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez sélectionner une vidéo d'abord." : "Please select a video first.");
                return;
            }

            const btn = document.getElementById('btnTestReframePreview');
            btn.disabled = true;
            btn.innerHTML = currentLang === 'fr' ? "Rendu Reframe 3s (GPU)..." : "Rendering 3s Reframe (GPU)...";

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
                btn.innerHTML = `<b data-i18n="btnPreviewReframe">${I18N[currentLang].btnPreviewReframe}</b>`;
            }
        }

        async function applyAndReturnToSubtitles() {
            const video = getCurrentGlobalVideo();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez sélectionner une vidéo 16:9." : "Please select a 16:9 video first.");
                return;
            }

            const btn = document.getElementById('btnApplyReframe');
            btn.disabled = true;

            const prog = trackRealtimeProgress(
                'reframe',
                'btnApplyReframe',
                'reframeBtnProgressFill',
                'reframeBtnText',
                'reframeProgressBar',
                'reframeProgressPct',
                'reframeProgressLabel',
                'reframeProgressWrap'
            );

            const payload = {
                video: video,
                mode: document.getElementById('reframeMode').value,
                manualPan: parseInt(document.getElementById('manualPan').value),
                sharpness: parseFloat(document.getElementById('sharpness').value) / 100.0,
                contrast: 1.0 + (parseFloat(document.getElementById('contrast').value) / 100.0),
                saturation: 1.0 + (parseFloat(document.getElementById('saturation').value) / 100.0),
                brightness: parseFloat(document.getElementById('brightness').value) / 100.0,
                vignette: parseFloat(document.getElementById('vignette').value) / 100.0,
                normalize_audio: document.getElementById('chkReframeNormalizeAudio') ? document.getElementById('chkReframeNormalizeAudio').checked : true,
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
                    prog.complete(currentLang === 'fr' ? 'Vidéo recadrée en 9:16 avec succès !' : 'Reframed to 9:16 successfully!');
                    window._wasReframedInSession = true;
                    const keepGroup = document.getElementById('keepRawReframedGroup');
                    if (keepGroup) keepGroup.style.display = 'flex';

                    sendToSubtitles(data.outputPath);
                } else {
                    prog.error(data.error || "Reframe failed");
                    alert("Error: " + (data.error || "Reframe failed"));
                }
            } catch (err) {
                prog.error(err.message);
                alert("Error: " + err.message);
            } finally {
                btn.disabled = false;
                const textEl = document.getElementById('reframeBtnText');
                if (textEl) textEl.innerHTML = `<span data-i18n="btnApplyReframe">${I18N[currentLang].btnApplyReframe}</span>`;
            }
        }

        async function exportReframeOnly() {
            const video = getCurrentGlobalVideo();
            if (!video) {
                alert(currentLang === 'fr' ? "Veuillez sélectionner une vidéo 16:9." : "Please select a 16:9 video first.");
                return;
            }

            const btn = document.getElementById('btnExportReframeOnly');
            btn.disabled = true;

            const prog = trackRealtimeProgress(
                'reframe',
                'btnApplyReframe',
                'reframeBtnProgressFill',
                'reframeBtnText',
                'reframeProgressBar',
                'reframeProgressPct',
                'reframeProgressLabel',
                'reframeProgressWrap'
            );

            const payload = {
                video: video,
                mode: document.getElementById('reframeMode').value,
                manualPan: parseInt(document.getElementById('manualPan').value),
                sharpness: parseFloat(document.getElementById('sharpness').value) / 100.0,
                contrast: 1.0 + (parseFloat(document.getElementById('contrast').value) / 100.0),
                saturation: 1.0 + (parseFloat(document.getElementById('saturation').value) / 100.0),
                brightness: parseFloat(document.getElementById('brightness').value) / 100.0,
                vignette: parseFloat(document.getElementById('vignette').value) / 100.0,
                normalize_audio: document.getElementById('chkReframeNormalizeAudio') ? document.getElementById('chkReframeNormalizeAudio').checked : true,
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
                    prog.complete(currentLang === 'fr' ? 'Vidéo 9:16 exportée avec succès !' : '9:16 Video exported successfully!');
                    const box = document.getElementById('reframeStatusBox');
                    if (box) {
                        const safePath = data.outputPath.replace(/\\\\/g, '\\\\\\\\');
                        box.style.display = 'block';
                        box.innerHTML = `
<div style="margin-bottom:8px;">
    <b>${I18N[currentLang].reframeExportSuccess}</b><br>
    <code style="word-break:break-all; font-size:0.82rem; color:var(--text-dim);">${data.outputPath}</code>
</div>
<div style="display:flex; flex-wrap:wrap; gap:8px; margin-top:10px;">
    <button type="button" class="btn-pill" onclick="openFileInExplorer('${safePath}')">
        ${I18N[currentLang].openFolderBtn}
    </button>
    <button type="button" class="btn-pill btn-pipeline" onclick="sendToSubtitles('${safePath}')" style="border-color:rgba(0,242,254,0.6); background:rgba(0,242,254,0.15);">
        Envoyer vers Sous-titres
    </button>
    <button type="button" class="btn-pill btn-pipeline" onclick="sendToSmartCut('${safePath}')">
        Envoyer vers AutoCut
    </button>
</div>`;
                    }
                    refreshCacheInfo();
                } else {
                    prog.error(data.error || "Reframe failed");
                    alert("Error: " + (data.error || "Reframe failed"));
                }
            } catch (err) {
                prog.error(err.message);
                alert("Error: " + err.message);
            } finally {
                btn.disabled = false;
            }
        }

        async function openFileInExplorer(filePath) {
            if (!filePath) return;
            try {
                const resp = await fetch('/api/open_folder', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ path: filePath })
                });
                const res = await resp.json();
                if (!res.success) {
                    console.warn("Could not open file explorer:", res);
                }
            } catch (err) {
                console.error("openFileInExplorer error:", err);
            }
        }

        async function refreshCacheInfo() {
            try {
                const resp = await fetch('/api/cache_info');
                const data = await resp.json();
                const badgeText = document.getElementById('cacheInfoText');
                if (badgeText) {
                    const count = (data.count || 0) + (data.temp_count || 0);
                    const size = data.size_mb || 0;
                    if (count === 0 && size === 0) {
                        badgeText.innerText = currentLang === 'fr' ? 'Cache : 0 Mo' : 'Cache: 0 MB';
                    } else {
                        badgeText.innerText = `Cache: ${size} MB (${count} ${currentLang === 'fr' ? 'fichiers' : 'files'})`;
                    }
                }
            } catch (err) {
                console.error("refreshCacheInfo error:", err);
            }
        }

        async function clearAppCache() {
            const confirmMsg = currentLang === 'fr'
                ? "Voulez-vous vraiment vider le cache de transcription Whisper et les aperçus temporaires ?"
                : "Are you sure you want to clear Whisper transcription cache and temporary files?";
            if (!confirm(confirmMsg)) return;

            try {
                const resp = await fetch('/api/clear_cache', { method: 'POST' });
                const data = await resp.json();
                await refreshCacheInfo();
                const msg = currentLang === 'fr'
                    ? `Cache vidé (${data.deleted || 0} fichiers supprimés).`
                    : `Cache cleared (${data.deleted || 0} files deleted).`;
                alert(msg);
            } catch (err) {
                alert("Error clearing cache: " + err.message);
            }
        }

        // Init language, controls and cache
        setLanguage(currentLang);
        applyPresetToControls();
        updateReframePreview();
        refreshCacheInfo();

        const engSelect = document.getElementById('smartCutEngine');
        if (engSelect) {
            engSelect.addEventListener('change', function() {
                const llmOpts = document.getElementById('smartCutLlmOptions');
                if (llmOpts) {
                    llmOpts.style.display = (this.value === 'llm') ? 'block' : 'none';
                }
            });
        }

        function setupDropZone(boxId, type) {
            const el = document.getElementById(boxId);
            if (!el) return;
            el.addEventListener('dragover', (e) => {
                e.preventDefault();
                el.classList.add('dropzone-active');
            });
            el.addEventListener('dragleave', (e) => {
                e.preventDefault();
                el.classList.remove('dropzone-active');
            });
            el.addEventListener('drop', (e) => {
                e.preventDefault();
                el.classList.remove('dropzone-active');
                if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    const f = e.dataTransfer.files[0];
                    const p = f.path || f.name;
                    if (type === 'srt') {
                        document.getElementById('srtPath').value = p;
                        onSrtPathChanged(p);
                    } else {
                        setGlobalVideo(p, type);
                    }
                }
            });
        }
        setupDropZone('subsVideoBox', 'video');
        setupDropZone('reframeVideoBox', 'reframe');
        setupDropZone('smartCutVideoBox', 'smartcut');
        setupDropZone('srtGroup', 'srt');
    </script>
</body>
</html>
"""


def native_file_picker(file_type="video") -> str:
    """Opens a native Windows Open File dialog in an isolated STA subprocess."""
    import platform
    import subprocess

    if platform.system() == "Windows":
        try:
            if file_type in ("video", "reframe_video"):
                flt = "Fichiers Video (*.mp4;*.mov;*.mkv;*.webm)|*.mp4;*.mov;*.mkv;*.webm|Tous les fichiers (*.*)|*.*"
                title = "Selectionner une video"
            elif file_type == "srt":
                flt = "Fichiers Sous-titres (*.srt;*.vtt)|*.srt;*.vtt|Tous les fichiers (*.*)|*.*"
                title = "Selectionner un fichier de sous-titres"
            else:
                flt = "Tous les fichiers (*.*)|*.*"
                title = "Selectionner un fichier"

            ps_script = f"""
Add-Type -AssemblyName System.Windows.Forms
$dialog = New-Object System.Windows.Forms.OpenFileDialog
$dialog.Filter = '{flt}'
$dialog.Title = '{title}'
$dialog.RestoreDirectory = $true
$dialog.AutoUpgradeEnabled = $true
$topForm = New-Object System.Windows.Forms.Form
$topForm.TopMost = $true
$topForm.StartPosition = [System.Windows.Forms.FormStartPosition]::CenterScreen
if ($dialog.ShowDialog($topForm) -eq [System.Windows.Forms.DialogResult]::OK) {{
    [Console]::Out.Write($dialog.FileName)
}}
$topForm.Dispose()
$dialog.Dispose()
"""
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-STA", "-Command", "-"],
                input=ps_script,
                capture_output=True,
                text=True,
                timeout=180
            )
            out = proc.stdout.strip()
            if out:
                return out
        except Exception as e:
            print(f"[!] native_file_picker STA: {e}")

    # Fallback to Tkinter only if PowerShell STA didn't return a file
    try:
        import tkinter as tk
        from tkinter import filedialog
        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        if file_type in ("video", "reframe_video"):
            ft = [("Video Files", "*.mp4;*.mov;*.mkv;*.webm"), ("All Files", "*.*")]
            title = "Select Video"
        else:
            ft = [("Subtitle Files", "*.srt;*.vtt"), ("All Files", "*.*")]
            title = "Select Subtitle File"
        selected = filedialog.askopenfilename(title=title, filetypes=ft)
        root.destroy()
        return selected or ""
    except Exception:
        return ""


def open_in_file_explorer(target_path: str) -> bool:
    """Opens the operating system file explorer highlighting or selecting the target file."""
    import platform
    import subprocess

    if not target_path:
        return False

    abs_path = os.path.abspath(target_path)
    if not os.path.exists(abs_path):
        parent_dir = os.path.dirname(abs_path)
        if os.path.exists(parent_dir):
            abs_path = parent_dir
        else:
            return False

    system = platform.system()
    try:
        if system == "Windows":
            norm = os.path.normpath(abs_path)
            if os.path.isfile(norm):
                subprocess.Popen(f'explorer.exe /select,"{norm}"')
            else:
                subprocess.Popen(f'explorer.exe "{norm}"')
            return True
        elif system == "Darwin":
            subprocess.Popen(["open", "-R", abs_path])
            return True
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(abs_path) if os.path.isfile(abs_path) else abs_path])
            return True
    except Exception as e:
        print(f"[!] Error opening file explorer: {e}")
        return False


def cleanup_stale_temp_files():
    """Removes orphan preview video and subtitle temp files from previous sessions."""
    td = tempfile.gettempdir()
    cleaned = 0
    try:
        for f in os.listdir(td):
            if f.startswith("submaxxing_"):
                fp = os.path.join(td, f)
                try:
                    age_s = time.time() - os.path.getmtime(fp)
                    if f.endswith(".ass") or age_s > 3600:
                        os.remove(fp)
                        cleaned += 1
                except Exception:
                    pass
    except Exception:
        pass
    if cleaned > 0:
        print(f"[i] Cleaned up {cleaned} stale temporary preview files.")


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


# Thread-safe global progress state for real-time frontend tracking
_PROGRESS_LOCK = threading.Lock()
_GLOBAL_PROGRESS = {
    "active": False,
    "type": "",          # "main" or "reframe"
    "percent": 0.0,
    "stage": "idle",     # "init", "whisper", "face_track", "nvenc", "done", "error"
    "message": "",
    "cur_sec": 0.0,
    "total_sec": 0.0,
    "speed": "1.0x",
    "done": False,
    "error": None,
    "timestamp": 0.0
}


def set_progress(
    active: bool = True,
    job_type: str = "main",
    percent: float = 0.0,
    stage: str = "",
    message: str = "",
    cur_sec: float = 0.0,
    total_sec: float = 0.0,
    speed: str = "1.0x",
    done: bool = False,
    error: Optional[str] = None
):
    with _PROGRESS_LOCK:
        _GLOBAL_PROGRESS["active"] = active
        _GLOBAL_PROGRESS["type"] = job_type
        _GLOBAL_PROGRESS["percent"] = round(float(percent), 1)
        _GLOBAL_PROGRESS["stage"] = stage
        _GLOBAL_PROGRESS["message"] = message
        _GLOBAL_PROGRESS["cur_sec"] = round(float(cur_sec), 2)
        _GLOBAL_PROGRESS["total_sec"] = round(float(total_sec), 2)
        _GLOBAL_PROGRESS["speed"] = speed
        _GLOBAL_PROGRESS["done"] = done
        _GLOBAL_PROGRESS["error"] = error
        _GLOBAL_PROGRESS["timestamp"] = time.time()


def get_progress() -> dict:
    with _PROGRESS_LOCK:
        return dict(_GLOBAL_PROGRESS)


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
        elif parsed.path == "/api/progress":
            self._send_json(get_progress())
            return
        elif parsed.path in ["/api/get_preview_video", "/api/get_reframe_preview"]:
            target = PREVIEW_FILE if parsed.path == "/api/get_preview_video" else REFRAME_PREVIEW_FILE
            if os.path.exists(target):
                self._serve_video_file(target)
            else:
                self.send_response(404)
                self.end_headers()
        elif parsed.path == "/api/stream_video":
            query = urllib.parse.parse_qs(parsed.query)
            vpath = query.get("path", [""])[0]
            if vpath and os.path.exists(vpath):
                self._serve_video_file(vpath)
            else:
                self.send_response(404)
                self.end_headers()
        elif parsed.path == "/api/check_cache":
            query = urllib.parse.parse_qs(parsed.query)
            vpath = query.get("video", [""])[0].strip(' "')
            cached = False
            if vpath and os.path.exists(vpath):
                from transcriber import load_cached_timings
                cached_data = load_cached_timings(vpath, "fr", "large-v3-turbo") or load_cached_timings(vpath, None, "large-v3-turbo")
                if cached_data:
                    cached = True
            self._send_json({"cached": cached})
            return
        elif parsed.path == "/api/cache_info":
            from transcriber import get_cache_info
            self._send_json(get_cache_info())
            return
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

        elif parsed.path == "/api/cache_info":
            from transcriber import get_cache_info
            self._send_json(get_cache_info())
            return

        elif parsed.path == "/api/clear_cache":
            from transcriber import clear_submaxxing_cache
            from reframe import clear_reframe_cache
            deleted = clear_submaxxing_cache()
            clear_reframe_cache()
            self._send_json({"success": True, "deleted": deleted})
            return

        elif parsed.path == "/api/open_folder":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
            data = json.loads(body)
            target_path = data.get("path", "").strip(' "')
            ok = open_in_file_explorer(target_path)
            self._send_json({"success": ok, "path": target_path})
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

        elif parsed.path == "/api/smartcut/analyze":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            self._handle_smartcut_analyze(data)
            return

        elif parsed.path == "/api/smartcut/render":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8")
            data = json.loads(body)
            self._handle_smartcut_render(data)
            return

    def _handle_smartcut_analyze(self, data: dict):
        try:
            video_path = data.get("video", "").strip(' "')
            if not video_path or not os.path.exists(video_path):
                self._send_json({"success": False, "error": "Fichier vidéo introuvable."})
                return

            min_silence = float(data.get("minSilence", 0.5))
            detect_fillers = bool(data.get("detectFillers", True))
            detect_stutters = bool(data.get("detectStutters", True))
            engine = data.get("engine", "heuristic")
            llm_url = data.get("llmUrl") if engine == "llm" else None
            llm_model = data.get("llmModel") if engine == "llm" else None

            from transcriber import transcribe_to_words
            from renderer import get_video_info
            from autocut import detect_cuts
            from topic_segmenter import segment_topics

            vinfo = get_video_info(video_path)
            total_duration = vinfo.get("duration", 0.0)

            words, _ = transcribe_to_words(
                video_path,
                model_name="large-v3-turbo",
                language=None,
                use_cache=True
            )

            cuts = detect_cuts(
                word_timings=words,
                video_duration=total_duration,
                min_silence_duration=min_silence,
                detect_fillers=detect_fillers,
                detect_stutters=detect_stutters
            )

            topics = segment_topics(
                word_timings=words,
                video_duration=total_duration,
                engine=engine,
                api_url=llm_url,
                model_name=llm_model
            )

            total_cut_sec = sum(c.duration for c in cuts)

            self._send_json({
                "success": True,
                "duration": total_duration,
                "words_count": len(words),
                "cuts": [c.to_dict() for c in cuts],
                "topics": [t.to_dict() for t in topics],
                "stats": {
                    "total_cuts": len(cuts),
                    "total_cut_duration": round(total_cut_sec, 2),
                    "estimated_new_duration": round(max(0.0, total_duration - total_cut_sec), 2)
                }
            })
        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

    def _handle_smartcut_render(self, data: dict):
        try:
            video_path = data.get("video", "").strip(' "')
            if not video_path or not os.path.exists(video_path):
                self._send_json({"success": False, "error": "Fichier vidéo introuvable."})
                return

            raw_cuts = data.get("cuts", [])
            selected_topic = data.get("selectedTopic")
            burn_subs = bool(data.get("burnSubtitles", True))
            preset_name = data.get("preset", "hormozi")

            from autocut import CutSegment, compute_keep_segments, shift_word_timings_for_cuts, render_autocut_video
            from renderer import get_video_info, render_subtitles_to_video
            from transcriber import transcribe_to_words
            from chunker import group_words_into_chunks
            from styles import PRESETS, chunks_to_ass

            vinfo = get_video_info(video_path)
            total_duration = vinfo.get("duration", 0.0)

            cuts = [
                CutSegment(
                    id=int(c["id"]),
                    start=float(c["start"]),
                    end=float(c["end"]),
                    duration=float(c["duration"]),
                    reason=str(c.get("reason", "silence")),
                    text=str(c.get("text", "")),
                    enabled=bool(c.get("enabled", True))
                )
                for c in raw_cuts
            ]

            if selected_topic and isinstance(selected_topic, dict):
                t_start = float(selected_topic.get("start", 0.0))
                t_end = float(selected_topic.get("end", total_duration))
                if t_start > 0.05:
                    cuts.insert(0, CutSegment(
                        id=999901,
                        start=0.0,
                        end=t_start,
                        duration=t_start,
                        reason="trim",
                        text="Hors extrait (début)",
                        enabled=True
                    ))
                if t_end < total_duration - 0.05:
                    cuts.append(CutSegment(
                        id=999902,
                        start=t_end,
                        end=total_duration,
                        duration=total_duration - t_end,
                        reason="trim",
                        text="Hors extrait (fin)",
                        enabled=True
                    ))

            keep_segs = compute_keep_segments(cuts, total_duration)
            if not keep_segs:
                self._send_json({"success": False, "error": "Aucun segment conservé (durée nulle)."})
                return

            base_dir = os.path.dirname(os.path.abspath(video_path))
            base_name = os.path.splitext(os.path.basename(video_path))[0]
            tag = f"_extrait{selected_topic.get('id')}" if selected_topic else "_dynamized"
            cut_output = os.path.join(base_dir, f"{base_name}{tag}_cut.mp4")
            normalize_audio = bool(data.get("normalize_audio", data.get("normalizeAudio", True)))

            render_autocut_video(
                input_path=video_path,
                output_path=cut_output,
                keep_segments=keep_segs,
                use_nvenc=True,
                normalize_audio=normalize_audio
            )

            final_output = cut_output

            if burn_subs:
                words, _ = transcribe_to_words(video_path, use_cache=True)
                shifted_words = shift_word_timings_for_cuts(words, cuts)
                if shifted_words:
                    chunks = group_words_into_chunks(shifted_words, max_words=2)
                    preset = PRESETS.get(preset_name, PRESETS["hormozi"])

                    cut_info = get_video_info(cut_output)
                    res_w = cut_info.get("width", 1080)
                    res_h = cut_info.get("height", 1920)

                    ass_path = os.path.splitext(cut_output)[0] + ".ass"
                    ass_content = chunks_to_ass(chunks, preset, play_res_x=res_w, play_res_y=res_h)
                    with open(ass_path, "w", encoding="utf-8") as f:
                        f.write(ass_content)

                    final_subbed = os.path.join(base_dir, f"{base_name}{tag}_subbed.mp4")
                    render_subtitles_to_video(
                        video_path=cut_output,
                        ass_path=ass_path,
                        output_path=final_subbed,
                        use_gpu=True,
                        compress=True,
                        normalize_audio=normalize_audio
                    )
                    final_output = final_subbed

            out_info = get_video_info(final_output)
            self._send_json({
                "success": True,
                "output": final_output,
                "final_duration": out_info.get("duration", 0.0)
            })

        except Exception as e:
            self._send_json({"success": False, "error": str(e)})

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
                from transcriber import transcribe_video, load_cached_timings
                actual_lang = None if lang == "auto" else lang
                cached = load_cached_timings(video_path, actual_lang, model_name)
                if cached:
                    chunks, _ = transcribe_video(
                        media_path=video_path,
                        model_name=model_name,
                        language=actual_lang,
                        max_words=words_per_chunk,
                        use_cache=True
                    )
                else:
                    # Fast 3-second preview: transcribe audio snippet in ~0.2s with true Whisper word timestamps
                    chunks, _ = transcribe_video(
                        media_path=video_path,
                        model_name=model_name,
                        language=actual_lang,
                        max_words=words_per_chunk,
                        duration_limit=3.0
                    )
            else:
                chunks = srt_to_chunks(srt_path, max_words=words_per_chunk, is_file=True)

            active_style = build_style_from_payload(data)

            ass_path = os.path.join(tempfile.gettempdir(), f"submaxxing_preview_{os.getpid()}.ass")
            ass_content = chunks_to_ass(chunks, active_style, play_res_x=width, play_res_y=height)
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)

            try:
                render_subtitles_to_video(
                    video_path=video_path,
                    ass_path=ass_path,
                    output_path=PREVIEW_FILE,
                    use_gpu=True,
                    duration_limit=3.0
                )
            finally:
                if os.path.exists(ass_path):
                    try:
                        os.remove(ass_path)
                    except Exception:
                        pass

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
                cb = None
            else:
                base_dir = os.path.dirname(video_path)
                base_name = os.path.splitext(os.path.basename(video_path))[0]
                output_path = os.path.join(base_dir, f"{base_name}_reframed_9x16.mp4")
                dur_limit = None

                set_progress(active=True, job_type="reframe", percent=2.0, stage="init", message="Analyzing video streams...")
                if mode == "face_track":
                    set_progress(active=True, job_type="reframe", percent=8.0, stage="face_track", message="OpenCV Face Tracking...")

                def cb(nv_pct, cur_s, tot_s, spd):
                    overall = 10.0 + (nv_pct / 100.0) * 88.0
                    set_progress(
                        active=True, job_type="reframe",
                        percent=overall, stage="nvenc",
                        message=f"GPU NVENC 9:16: {cur_s:.1f}s / {tot_s:.1f}s @ {spd}",
                        cur_sec=cur_s, total_sec=tot_s, speed=spd
                    )

            compress = data.get("compress", True)
            normalize_audio = data.get("normalizeAudio", data.get("normalize_audio", True))
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
                use_gpu=True,
                compress=compress,
                progress_callback=cb,
                normalize_audio=normalize_audio
            )

            if not preview_only:
                set_progress(active=False, job_type="reframe", percent=100.0, stage="done", message="Reframe complete!", done=True)

            self._send_json({"success": True, "outputPath": output_path})
        except Exception as e:
            import traceback
            print(f"[!] Reframe error: {traceback.format_exc()}")
            set_progress(active=False, job_type="reframe", percent=0.0, stage="error", message=str(e), done=True, error=str(e))
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
        compress = data.get("compress", True)
        export_sub_files = data.get("exportSubFiles", False)
        keep_raw_reframed = data.get("keepRawReframed", False)
        was_reframed = data.get("wasReframed", False)
        normalize_audio = data.get("normalizeAudio", True)

        if not video_path or not os.path.exists(video_path):
            self._send_json({"success": False, "error": f"Video file not found: '{video_path}'"})
            return

        temp_ass_path = None
        try:
            dir_name = os.path.dirname(os.path.abspath(video_path))
            file_stem = os.path.splitext(os.path.basename(video_path))[0]

            is_intermediate_reframe = was_reframed or file_stem.endswith("_reframed_9x16")
            if is_intermediate_reframe:
                clean_stem = file_stem.replace("_reframed_9x16", "")
                final_mp4 = os.path.join(dir_name, f"{clean_stem}_9x16_subbed.mp4")
            else:
                clean_stem = file_stem
                final_mp4 = os.path.join(dir_name, f"{clean_stem}_subbed.mp4")

            mov_out = os.path.join(dir_name, f"{clean_stem}_overlay.mov")
            webm_out = os.path.join(dir_name, f"{clean_stem}_overlay.webm")

            if export_sub_files:
                ass_path = os.path.join(dir_name, f"{clean_stem}_submaxxing.ass")
            else:
                temp_fd, temp_ass_path = tempfile.mkstemp(suffix="_submaxxing.ass")
                os.close(temp_fd)
                ass_path = temp_ass_path

            set_progress(active=True, job_type="main", percent=2.0, stage="init", message="Reading video metadata...")
            log(f"[*] Reading video metadata: '{video_path}'...")
            vinfo = get_video_info(video_path)
            width, height, duration, fps = vinfo["width"], vinfo["height"], vinfo["duration"], vinfo["fps"]
            log(f"    Format: {width}x{height} | Duration: {duration:.2f}s | FPS: {fps:.2f}")

            if auto_transcribe or not srt_path:
                set_progress(active=True, job_type="main", percent=5.0, stage="whisper", message=f"Whisper AI '{model_name}' on GPU (CUDA)...")
                log(f"[*] Local Whisper '{model_name}' on GPU (language: {lang})...")
                from transcriber import transcribe_video
                actual_lang = None if lang == "auto" else lang

                def whisper_cb(cur_audio_s, tot_audio_s):
                    if tot_audio_s > 0:
                        w_pct = 5.0 + (cur_audio_s / tot_audio_s) * 23.0
                        set_progress(
                            active=True, job_type="main",
                            percent=w_pct, stage="whisper",
                            message=f"Whisper AI: {cur_audio_s:.1f}s / {tot_audio_s:.1f}s",
                            cur_sec=cur_audio_s, total_sec=tot_audio_s
                        )

                chunks, srt_content = transcribe_video(
                    media_path=video_path,
                    model_name=model_name,
                    language=actual_lang,
                    max_words=words_per_chunk,
                    use_cache=True,
                    progress_callback=whisper_cb
                )
                if export_sub_files:
                    saved_srt = os.path.join(dir_name, f"{clean_stem}_transcribed.srt")
                    with open(saved_srt, "w", encoding="utf-8") as f:
                        f.write(srt_content)
                    log(f"[+] Saved generated SRT to: '{saved_srt}'")
                else:
                    log("[i] Clean folder mode active: raw .srt file not exported.")
            else:
                if not os.path.exists(srt_path):
                    self._send_json({"success": False, "error": f"SRT file not found: '{srt_path}'"})
                    return
                set_progress(active=True, job_type="main", percent=5.0, stage="srt", message="Parsing SRT subtitles...")
                log(f"[*] Slicing SRT '{srt_path}' (max {words_per_chunk} words/chunk)...")
                chunks = srt_to_chunks(srt_path, max_words=words_per_chunk, is_file=True)
                log(f"[+] Sliced into {len(chunks)} chunks.")

            active_style = build_style_from_payload(data)

            log(f"[*] Generating ASS subtitle file ({active_style.name})...")
            ass_content = chunks_to_ass(chunks, active_style, play_res_x=width, play_res_y=height)
            with open(ass_path, "w", encoding="utf-8") as f:
                f.write(ass_content)
            if export_sub_files:
                log(f"[+] ASS file created: '{ass_path}'")
            else:
                log("[i] Clean folder mode active: ASS subtitles processed via temp cache.")

            start_pct = 30.0 if (auto_transcribe or not srt_path) else 6.0
            span = 98.0 - start_pct

            def render_cb(nv_pct, cur_s, tot_s, spd):
                overall = start_pct + (nv_pct / 100.0) * span
                set_progress(
                    active=True, job_type="main",
                    percent=overall, stage="nvenc",
                    message=f"GPU NVENC: {cur_s:.1f}s / {tot_s:.1f}s @ {spd}",
                    cur_sec=cur_s, total_sec=tot_s, speed=spd
                )

            if render_type in ["overlay_mov", "both"]:
                log(f"[*] Rendering transparent ProRes 4444 overlay (multithreaded)...")
                render_transparent_overlay(
                    ass_path=ass_path,
                    output_path=mov_out,
                    duration=duration,
                    width=width,
                    height=height,
                    fps=fps,
                    format_type="mov",
                    progress_callback=render_cb if render_type == "overlay_mov" else None
                )
                log(f"[+] ProRes 4444 overlay ready: '{mov_out}'")

            if render_type == "overlay_webm":
                log(f"[*] Rendering transparent WebM overlay (VP9 multithreaded)...")
                render_transparent_overlay(
                    ass_path=ass_path,
                    output_path=webm_out,
                    duration=duration,
                    width=width,
                    height=height,
                    fps=fps,
                    format_type="webm",
                    progress_callback=render_cb
                )
                log(f"[+] WebM overlay ready: '{webm_out}'")

            if render_type in ["burn", "both"]:
                log(f"[*] GPU NVENC accelerated rendering{' (with smart web compression)' if compress else ''}...")
                render_subtitles_to_video(
                    video_path=video_path,
                    ass_path=ass_path,
                    output_path=final_mp4,
                    use_gpu=True,
                    compress=compress,
                    progress_callback=render_cb,
                    normalize_audio=normalize_audio
                )
                log(f"[+] Final video rendered: '{final_mp4}'")

            # Clean up intermediate raw reframed video if chained and not requested to keep
            if is_intermediate_reframe and not keep_raw_reframed:
                if os.path.exists(video_path) and os.path.abspath(video_path) != os.path.abspath(final_mp4):
                    try:
                        os.remove(video_path)
                        log(f"[i] Clean folder mode: intermediate raw 9:16 file '{os.path.basename(video_path)}' cleaned up.")
                    except Exception as clean_err:
                        log(f"[!] Note: couldn't delete intermediate file '{video_path}': {clean_err}")

            set_progress(active=False, job_type="main", percent=100.0, stage="done", message="Export complete!", done=True)
            log("\n[+] Export termine avec succes!")
            self._send_json({"success": True, "logs": "\n".join(logs), "outputPath": final_mp4})

        except Exception as e:
            import traceback
            set_progress(active=False, job_type="main", percent=0.0, stage="error", message=str(e), done=True, error=str(e))
            log(f"[!] Error: {traceback.format_exc()}")
            self._send_json({"success": False, "error": str(e), "logs": "\n".join(logs)})
        finally:
            if temp_ass_path and os.path.exists(temp_ass_path):
                try:
                    os.remove(temp_ass_path)
                except Exception:
                    pass

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
    cleanup_stale_temp_files()
    server = None
    try:
        server = ThreadedHTTPServer(("127.0.0.1", PORT), SubHandler)
    except OSError:
        print(f"[!] Port {PORT} occupe, tentative de liberation...")
        try:
            import subprocess
            res = subprocess.run(f'netstat -ano | findstr :{PORT}', shell=True, capture_output=True, text=True)
            if res.returncode == 0 and res.stdout:
                for line in res.stdout.strip().splitlines():
                    parts = line.strip().split()
                    if len(parts) >= 5 and f":{PORT}" in parts[1]:
                        pid = parts[-1]
                        if pid.isdigit() and int(pid) != os.getpid():
                            subprocess.run(f"taskkill /f /pid {pid}", shell=True, capture_output=True)
                time.sleep(0.5)
            server = ThreadedHTTPServer(("127.0.0.1", PORT), SubHandler)
        except Exception as e:
            print(f"[!] Impossible de lier au port {PORT} ({e}), assignation d'un port automatique...")
            server = ThreadedHTTPServer(("127.0.0.1", 0), SubHandler)

    bound_port = server.server_address[1]
    url = f"http://127.0.0.1:{bound_port}"
    print(f"\n=======================================================")
    print(f"[*] Submaxxing Studio Pro - Serveur actif")
    print(f"[*] Interface Web disponible sur : {url}")
    print(f"=======================================================\n")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArret du serveur.")


if __name__ == "__main__":
    run_server()
