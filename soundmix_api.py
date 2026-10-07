#!/usr/bin/env python3

# -*- coding: utf-8 -*-

"""صوت ميكس — أداة محلية لمزج أي ملف صوتي مع خلفية بيئية خفيفة.



المتطلبات: Python 3.9+ وFFmpeg. لا تُرفع الملفات إلى الإنترنت؛ يُنزّل التطبيق

المؤثرات المختارة من Mixkit عند الحاجة ويخزنها مؤقتًا محليًا.

"""

from __future__ import annotations



import argparse

import email.policy

import html
import hmac

import json

import mimetypes

import os

import re

import shutil

import subprocess

import sys

import tempfile

import threading

import urllib.error

import urllib.parse

import urllib.request

import webbrowser

from email.parser import BytesParser

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from pathlib import Path



APP_NAME = "صوت ميكس"

HOST = os.environ.get("SOUNDMIX_HOST", "0.0.0.0")
API_KEY = os.environ.get("SOUNDMIX_API_KEY", "")
CORS_ORIGIN = os.environ.get("SOUNDMIX_CORS_ORIGIN", "*")

DEFAULT_PORT = int(os.environ.get("PORT", "10000"))

MAX_FILE_BYTES = 300 * 1024 * 1024

MAX_BODY_BYTES = MAX_FILE_BYTES * 2 + 2 * 1024 * 1024

MAX_SOUND_BYTES = 40 * 1024 * 1024

CACHE_DIR = Path.home() / ".soundmix" / "cache"

MIXKIT_LICENSE = "https://mixkit.co/license/#sfxFree"



ALLOWED_AUDIO_EXTENSIONS = {

    ".mp3", ".wav", ".m4a", ".aac", ".ogg", ".oga", ".opus",

    ".flac", ".wma", ".aiff", ".aif", ".mp4", ".webm"

}



BACKGROUNDS = {

    "rain": {

        "title": "مطر خفيف",

        "description": "رذاذ هادئ ومتواصل؛ مناسب للكلام والتسجيلات الهادئة.",

        "symbol": "rain",

        "asset_id": "2393",

        "source": "https://mixkit.co/free-sound-effects/rain/",

        "asset_title": "Light rain loop",

    },

    "traffic": {

        "title": "حركة سيارات",

        "description": "ضجيج شارع وسيارات بعيد، من دون أن يطغى على الصوت الأساسي.",

        "symbol": "traffic",

        "asset_id": "2930",

        "source": "https://mixkit.co/free-sound-effects/traffic/",

        "asset_title": "City traffic background ambience",

    },

    "market": {

        "title": "سوق ومركز تجاري",

        "description": "همهمة أشخاص وأجواء مكان عام مزدحم باعتدال.",

        "symbol": "market",

        "asset_id": "377",

        "source": "https://mixkit.co/free-sound-effects/public-places/",

        "asset_title": "Shopping center crowd",

    },

    "street": {

        "title": "شارع وناس",

        "description": "أجواء شارع عامة وخطوات خفيفة لأجواء واقعية.",

        "symbol": "street",

        "asset_id": "375",

        "source": "https://mixkit.co/free-sound-effects/public-places/",

        "asset_title": "Street ambience with walking people",

    },

    "neighborhood": {

        "title": "حيّ هادئ",

        "description": "أجواء أطراف المدينة مع أصوات طبيعة خفيفة.",

        "symbol": "neighborhood",

        "asset_id": "371",

        "source": "https://mixkit.co/free-sound-effects/traffic/",

        "asset_title": "Sub urban ambience and birds",

    },

}



ICONS = {

    "rain": '<path d="M7 15.5a4.5 4.5 0 0 1 .8-8.93A6 6 0 0 1 19 8.8a3.4 3.4 0 0 1-.4 6.7H7Z"/><path d="m9 18-1 2m6-2-1 2m6-2-1 2"/>',

    "traffic": '<path d="M4 16.5h16l-1.6-6a2 2 0 0 0-1.9-1.5h-9a2 2 0 0 0-1.9 1.5l-1.6 6Z"/><path d="M6 16.5v2m12-2v2M7 9l1-3h8l1 3M2 12h2m16 0h2"/><circle cx="7.5" cy="16.5" r="1"/><circle cx="16.5" cy="16.5" r="1"/>',

    "market": '<path d="M4 10h16l-1-5H5l-1 5Z"/><path d="M5 10v10h14V10M8 20v-6h8v6"/><path d="M4 10a2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0 2 2 0 0 0 4 0"/>',

    "street": '<path d="M4 20V8l8-4 8 4v12M8 20v-6h8v6"/><path d="M2 10h2m16 0h2M12 4V2"/><circle cx="12" cy="10" r="1"/>',

    "neighborhood": '<path d="m3 11 9-7 9 7M5 10v10h14V10M9 20v-6h6v6"/><path d="M19 5c1.5 0 2.5 1 2.5 2.3M2 6c1.4 0 2.4 1 2.4 2.3"/>',

}





def find_ffmpeg() -> str | None:

    """Return an installed FFmpeg executable, including imageio-ffmpeg if present."""

    executable = shutil.which("ffmpeg")

    if executable:

        return executable

    try:

        import imageio_ffmpeg  # type: ignore

        candidate = imageio_ffmpeg.get_ffmpeg_exe()

        if candidate and Path(candidate).is_file():

            return candidate

    except Exception:

        pass

    return None





def cached_sound(key: str) -> Path:

    if key not in BACKGROUNDS:

        raise ValueError("الخلفية المختارة غير معروفة.")

    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    dest = CACHE_DIR / (BACKGROUNDS[key]["asset_id"] + ".mp3")

    if dest.is_file() and dest.stat().st_size > 2048:

        return dest

    url = f"https://assets.mixkit.co/active_storage/sfx/{BACKGROUNDS[key]['asset_id']}/{BACKGROUNDS[key]['asset_id']}-preview.mp3"

    request = urllib.request.Request(

        url,

        headers={"User-Agent": "SoundMix-Python/1.0 (local audio mixer)", "Accept": "audio/mpeg,*/*;q=0.8"},

    )

    temp = dest.with_suffix(".part")

    try:

        with urllib.request.urlopen(request, timeout=45) as response, temp.open("wb") as output:

            declared = int(response.headers.get("Content-Length", "0") or 0)

            if declared > MAX_SOUND_BYTES:

                raise ValueError("حجم مؤثر الخلفية أكبر من الحد المسموح.")

            received = 0

            while True:

                chunk = response.read(256 * 1024)

                if not chunk:

                    break

                received += len(chunk)

                if received > MAX_SOUND_BYTES:

                    raise ValueError("حجم مؤثر الخلفية أكبر من الحد المسموح.")

                output.write(chunk)

        if received < 2048:

            raise ValueError("لم يصل ملف الصوت كاملًا من Mixkit.")

        temp.replace(dest)

        return dest

    except urllib.error.HTTPError as exc:

        temp.unlink(missing_ok=True)

        raise RuntimeError(f"تعذر تنزيل المؤثر من Mixkit (HTTP {exc.code}). تحقق من اتصال الإنترنت وحاول مجددًا.") from exc

    except Exception:

        temp.unlink(missing_ok=True)

        raise





def render_background_cards() -> str:

    cards = []

    for index, (key, item) in enumerate(BACKGROUNDS.items()):

        checked = " checked" if index == 0 else ""

        cards.append(

            f'''<label class="scene-card" for="scene-{key}">

                <input id="scene-{key}" type="radio" name="background" value="{key}"{checked}>

                <span class="scene-icon"><svg viewBox="0 0 24 24" aria-hidden="true">{ICONS[item['symbol']]}</svg></span>

                <span class="scene-copy"><b>{html.escape(item['title'])}</b><small>{html.escape(item['description'])}</small></span>

                <button class="listen" type="button" data-listen="{key}" aria-label="استمع إلى {html.escape(item['title'])}"><svg viewBox="0 0 24 24"><path d="m9 6 10 6-10 6V6Z"/></svg></button>

                <span class="selected-mark" aria-hidden="true">✓</span>

            </label>'''

        )

    return "\n".join(cards)





PAGE = r'''<!doctype html>

<html lang="ar" dir="rtl">

<head>

<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">

<meta name="theme-color" content="#0b1719"><title>صوت ميكس — مزج صوتي محلي</title>

<style>

:root{color-scheme:dark;--bg:#0b1719;--panel:#102225;--panel2:#142a2d;--line:#294044;--text:#edf7f4;--muted:#95aaa7;--mint:#76e0c0;--mint2:#b8f3de;--amber:#ffc976;--danger:#ff9a8e;--radius:20px}

*{box-sizing:border-box}body{margin:0;background:radial-gradient(ellipse at 84% -4%,rgba(60,150,126,.16),transparent 38%),radial-gradient(ellipse at 4% 27%,rgba(31,83,88,.28),transparent 32%),var(--bg);color:var(--text);font-family:Tahoma,"Segoe UI",Arial,sans-serif;min-height:100vh}button,input,select{font:inherit}button{cursor:pointer}.shell{max-width:1180px;margin:auto;padding:25px 24px 42px}.topbar{display:flex;align-items:center;justify-content:space-between;padding:8px 2px 26px;border-bottom:1px solid rgba(160,202,192,.12)}.brand{display:flex;align-items:center;gap:12px}.brand-mark{width:42px;height:42px;border-radius:13px;background:linear-gradient(140deg,#9af2d4,#55c7a8);display:grid;place-items:center;color:#082122;box-shadow:0 8px 30px #64d7b626}.brand-mark svg{width:24px;height:24px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.brand-title{font-size:18px;font-weight:800;letter-spacing:-.4px}.brand-sub{display:block;color:var(--muted);font-size:11px;margin-top:3px;font-weight:400}.local-pill{display:inline-flex;align-items:center;gap:8px;color:#b9dfd2;border:1px solid #31554d;background:#122a26;border-radius:99px;padding:9px 13px;font-size:12px}.local-pill i{width:7px;height:7px;border-radius:50%;background:#71dfb5;box-shadow:0 0 0 4px #71dfb51c}.hero{display:flex;align-items:flex-end;justify-content:space-between;padding:32px 2px 25px;gap:20px}.eyebrow{color:var(--mint);font-size:11px;letter-spacing:.08em;font-weight:700}.hero h1{font-size:clamp(26px,4.4vw,43px);letter-spacing:-1.5px;margin:11px 0 10px;line-height:1.25}.hero p{margin:0;color:#a8bdb8;max-width:610px;line-height:1.9;font-size:14px}.hero-note{color:#bacdc8;display:flex;align-items:center;gap:10px;font-size:12px;white-space:nowrap;padding-bottom:5px}.hero-note svg{width:19px;height:19px;stroke:var(--mint);fill:none;stroke-width:1.7}.steps{display:flex;gap:10px;margin:4px 0 18px;align-items:center;color:#7d9691;font-size:11px}.step{display:flex;align-items:center;gap:8px}.step em{font-style:normal;width:21px;height:21px;border-radius:50%;display:grid;place-items:center;border:1px solid #395255;color:#9db6b1;font-size:10px}.step.active{color:#dff6ed}.step.active em{background:#8fe9c9;color:#06201d;border-color:#8fe9c9}.step-line{height:1px;background:#2d4144;width:34px}.workspace{display:grid;grid-template-columns:minmax(0,1.13fr) minmax(340px,.87fr);gap:16px;align-items:start}.panel{background:linear-gradient(145deg,rgba(18,39,42,.96),rgba(13,30,32,.96));border:1px solid rgba(145,190,178,.17);border-radius:var(--radius);padding:22px;box-shadow:0 18px 60px #030b0d32}.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:12px;margin-bottom:17px}.step-label{color:var(--mint);font-size:10px;letter-spacing:.12em;font-weight:800}.panel h2{font-size:17px;margin:6px 0 0;letter-spacing:-.2px}.panel-desc{color:var(--muted);font-size:12px;margin:7px 0 0;line-height:1.75}.upload-zone{border:1px dashed #45635f;border-radius:17px;background:linear-gradient(130deg,#112a2b,#102225);min-height:176px;display:grid;place-items:center;text-align:center;padding:22px 18px;transition:.18s ease;cursor:pointer}.upload-zone:hover,.upload-zone.drag{border-color:var(--mint);background:#15302e;transform:translateY(-1px)}.upload-icon{width:46px;height:46px;border-radius:15px;background:#1b3936;display:grid;place-items:center;margin:0 auto 12px;color:var(--mint)}.upload-icon svg{width:23px;height:23px;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}.upload-title{font-size:14px;font-weight:700}.upload-hint{font-size:11px;color:#8ea6a1;margin-top:7px}.file-meta{display:none;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;border:1px solid #31504a;background:#132c29;border-radius:13px;margin-top:12px}.file-meta.show{display:flex}.file-name{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:12px}.file-size{color:#9cb4ac;white-space:nowrap;font-size:11px}.audio-preview{display:none;width:100%;height:36px;margin-top:12px}.audio-preview.show{display:block}.rule{height:1px;background:var(--line);margin:20px 0}.section-title{font-size:13px;font-weight:700;margin-bottom:4px}.section-sub{font-size:11px;color:var(--muted);margin-bottom:13px}.scenes{display:grid;grid-template-columns:1fr 1fr;gap:9px}.scene-card{position:relative;display:flex;align-items:center;gap:10px;min-height:79px;padding:11px 10px;border:1px solid #2b4144;background:#102225;border-radius:15px;cursor:pointer;transition:.16s ease}.scene-card:hover{border-color:#53716b;background:#142a2b}.scene-card:has(input:checked){border-color:#6cc7a9;background:linear-gradient(135deg,#193633,#132a2b);box-shadow:inset 0 0 0 1px #69c7a936}.scene-card input{position:absolute;opacity:0;pointer-events:none}.scene-icon{flex:0 0 35px;height:35px;display:grid;place-items:center;border-radius:11px;background:#1c3837;color:#80dfbf}.scene-icon svg{width:21px;height:21px;fill:none;stroke:currentColor;stroke-width:1.55;stroke-linecap:round;stroke-linejoin:round}.scene-copy{min-width:0;display:flex;flex-direction:column;gap:4px;flex:1}.scene-copy b{font-size:11.5px;font-weight:700}.scene-copy small{font-size:9.5px;color:#8da49f;line-height:1.45}.listen{flex:0 0 27px;width:27px;height:27px;border:1px solid #36504f;border-radius:9px;background:#142c2d;color:#b4ded0;display:grid;place-items:center;padding:0}.listen:hover{background:#20413c;color:white}.listen svg{width:13px;height:13px;fill:currentColor;stroke:currentColor;stroke-width:1.5;stroke-linejoin:round}.selected-mark{display:none;position:absolute;top:7px;left:8px;color:#86e6c1;font-size:11px}.scene-card:has(input:checked) .selected-mark{display:block}.custom-card{grid-column:1/-1;display:flex;align-items:center;gap:10px;padding:11px 13px;border:1px solid #2b4144;background:#102225;border-radius:14px;cursor:pointer}.custom-card:has(input:checked){border-color:#6cc7a9;background:#17312f}.custom-card input{accent-color:#76e0c0}.custom-card b{font-size:11px}.custom-card small{display:block;color:var(--muted);font-size:10px;margin-top:4px}.custom-file{display:none;grid-column:1/-1;padding:10px;border:1px dashed #45635f;border-radius:12px;background:#102225}.custom-file.show{display:block}.custom-file input{max-width:100%;font-size:11px;color:#acc0bb}.mix-controls{padding-top:1px}.slider-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.slider-title{font-size:12px;font-weight:700}.slider-value{font-size:12px;color:var(--mint);font-weight:700;direction:ltr}.range{width:100%;height:4px;appearance:none;border-radius:8px;background:linear-gradient(90deg,#76e0c0 0%,#76e0c0 25%,#304547 25%);outline:none;margin:10px 0 5px;direction:ltr}.range::-webkit-slider-thumb{appearance:none;width:16px;height:16px;border-radius:50%;background:#b5f2dc;border:3px solid #12322d;box-shadow:0 0 0 1px #76e0c0}.range::-moz-range-thumb{width:11px;height:11px;border-radius:50%;background:#b5f2dc;border:3px solid #12322d;box-shadow:0 0 0 1px #76e0c0}.slider-help{display:flex;justify-content:space-between;color:#819993;font-size:10px}.format-row{display:flex;align-items:center;justify-content:space-between;margin-top:18px;gap:12px}.format-label{font-size:12px;font-weight:700}.format-label small{display:block;font-size:10px;font-weight:400;color:var(--muted);margin-top:4px}.format-select{background:#14292b;color:#e9f5f1;border:1px solid #355052;border-radius:10px;padding:9px 30px 9px 12px;direction:rtl;font-size:12px;outline:none}.privacy-note{display:flex;gap:9px;align-items:flex-start;color:#8ea7a0;font-size:10px;line-height:1.8;background:#10201f;border:1px solid #263d3b;padding:11px 12px;border-radius:12px;margin-top:16px}.privacy-note svg{flex:0 0 16px;width:16px;height:16px;stroke:#88d7b9;fill:none;stroke-width:1.7;margin-top:1px}.export-btn{width:100%;margin-top:16px;border:0;border-radius:13px;background:linear-gradient(120deg,#b2f1d7,#6bd4b1);color:#09221e;min-height:48px;font-size:13px;font-weight:800;box-shadow:0 10px 24px #52c79c26;transition:.18s}.export-btn:hover:not(:disabled){filter:brightness(1.06);transform:translateY(-1px)}.export-btn:disabled{opacity:.42;cursor:not-allowed;box-shadow:none}.output{display:none;margin-top:15px;border:1px solid #3d6657;background:#102a24;border-radius:14px;padding:14px}.output.show{display:block}.output-title{color:#a9efd1;font-size:12px;font-weight:700;margin-bottom:8px}.output audio{width:100%;height:34px}.download-link{display:inline-flex;margin-top:9px;padding:9px 13px;border-radius:10px;background:#8ee4c2;color:#0b2821;text-decoration:none;font-size:11px;font-weight:800}.status{display:none;margin-top:13px;border-radius:11px;padding:11px 13px;font-size:11px;line-height:1.6}.status.show{display:block}.status.error{border:1px solid #68443f;background:#301d1b;color:#ffc0b6}.status.ok{border:1px solid #365e50;background:#142d25;color:#b6efd2}.status.busy{border:1px solid #415b58;background:#172725;color:#b9d8ce}.side-panel{position:sticky;top:15px}.mix-visual{height:70px;margin-top:19px;border-radius:13px;background:linear-gradient(110deg,#122b2c,#183532 52%,#132726);border:1px solid #294442;display:flex;align-items:center;justify-content:center;gap:4px;overflow:hidden;position:relative}.mix-visual:before,.mix-visual:after{content:"";position:absolute;top:0;bottom:0;width:15%;z-index:1}.mix-visual:before{right:0;background:linear-gradient(270deg,#142c2d,transparent)}.mix-visual:after{left:0;background:linear-gradient(90deg,#142c2d,transparent)}.bar{width:3px;border-radius:10px;background:#5ec9a8;opacity:.75;animation:pulse 1.2s ease-in-out infinite alternate;animation-delay:calc(var(--i)*-70ms)}.bar:nth-child(3n){background:#b0e9cf;opacity:.55}.bar:nth-child(5n){background:#d9a86c;opacity:.6}@keyframes pulse{from{transform:scaleY(.36);opacity:.4}to{transform:scaleY(1);opacity:.82}}.mix-caption{text-align:center;font-size:10px;color:#8da8a0;margin-top:9px}.howto{margin-top:18px;border-top:1px solid #294044;padding-top:17px}.howto h3{font-size:12px;margin:0 0 10px}.howto-row{display:flex;gap:10px;align-items:flex-start;margin:9px 0;color:#a4b9b3;font-size:10px;line-height:1.65}.num{flex:0 0 20px;height:20px;display:grid;place-items:center;background:#1b3534;border-radius:7px;color:#8adaba;font-size:10px}.legal{font-size:9px;color:#718782;line-height:1.7;margin-top:14px}.legal a{color:#99cbbc;text-decoration:underline;text-underline-offset:2px}.footer{display:flex;justify-content:space-between;gap:12px;color:#718782;font-size:10px;padding:19px 4px 0}.footer a{color:#8dcbb6;text-decoration:none}.spinner{display:inline-block;width:13px;height:13px;border:2px solid #153e37;border-top-color:transparent;border-radius:50%;vertical-align:-2px;animation:spin .7s linear infinite;margin-left:7px}@keyframes spin{to{transform:rotate(360deg)}}

@media(max-width:850px){.workspace{grid-template-columns:1fr}.side-panel{position:static}.hero{align-items:flex-start;flex-direction:column}.hero-note{padding:0}.panel{padding:18px}.topbar{padding-bottom:20px}}

@media(max-width:520px){.shell{padding:16px 13px 28px}.local-pill{font-size:10px;padding:8px 10px}.hero{padding-top:27px}.steps{gap:7px;font-size:9px}.step-line{width:14px}.workspace{gap:12px}.scenes{grid-template-columns:1fr}.custom-card,.custom-file{grid-column:auto}.scene-card{min-height:70px}.panel{padding:15px}.footer{flex-direction:column}}

</style>

</head>

<body>

<div class="shell">

<header class="topbar"><div class="brand"><div class="brand-mark"><svg viewBox="0 0 24 24"><path d="M3 12h2l2-6 4 12 3-9 2 6 2-3h3"/></svg></div><div><div class="brand-title">صوت ميكس</div><span class="brand-sub">مساحة مزج صوتي محلية</span></div></div><div class="local-pill"><i></i> يعمل على جهازك</div></header>

<section class="hero"><div><div class="eyebrow">طبقة صوتية، إحساس مختلف</div><h1>أضف أجواءً واقعية إلى صوتك.</h1><p>ارفع تسجيلًا، اختر خلفية من المطر أو الشارع أو السوق، واضبطها بهدوء. ملفك يبقى على جهازك ويخرج جاهزًا للتنزيل.</p></div><div class="hero-note"><svg viewBox="0 0 24 24"><path d="M12 3 4.5 6v5.5c0 4.6 3.2 7.6 7.5 9.5 4.3-1.9 7.5-4.9 7.5-9.5V6L12 3Z"/><path d="m9 12 2 2 4-4"/></svg> لا نرفع تسجيلك لأي خدمة</div></section>

<div class="steps"><span class="step active"><em>١</em> الصوت الأصلي</span><span class="step-line"></span><span class="step active"><em>٢</em> الخلفية</span><span class="step-line"></span><span class="step"><em>٣</em> التصدير</span></div>

<form id="mixForm" class="workspace" enctype="multipart/form-data">

<section class="panel">

<div class="panel-head"><div><div class="step-label">01 / SOURCE</div><h2>اختر الصوت الأساسي</h2><p class="panel-desc">يدعم MP3 وWAV وM4A وOGG وOGA وOpus وFLAC وصيغًا أخرى يتعرف عليها FFmpeg.</p></div></div>

<label class="upload-zone" id="dropZone" for="sourceFile"><input type="file" id="sourceFile" name="audio" accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,.opus,.flac,.wma,.aiff,.aif,.mp4,.webm" hidden><span><span class="upload-icon"><svg viewBox="0 0 24 24"><path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5"/><path d="M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4"/></svg></span><span class="upload-title">اسحب ملفك الصوتي إلى هنا</span><span class="upload-hint">أو انقر للاستعراض · حد أقصى 300 ميغابايت</span></span></label>

<div class="file-meta" id="sourceMeta"><span class="file-name" id="sourceName"></span><span class="file-size" id="sourceSize"></span></div><audio id="sourcePreview" class="audio-preview" controls></audio>

<div class="rule"></div><div class="section-title">اختر المشهد الصوتي</div><div class="section-sub">استمع إلى العينات أولًا؛ ستتكرر الخلفية بهدوء لتواكب طول تسجيلك.</div>

<div class="scenes">__SCENE_CARDS__<label class="custom-card" for="scene-custom"><input type="radio" id="scene-custom" name="background" value="custom"><span><b>خلفية من ملفك</b><small>ارفع أي تسجيل خلفية تملكه من جهازك.</small></span></label><div class="custom-file" id="customWrap"><input type="file" id="customFile" name="custom_background" accept="audio/*,.mp3,.wav,.m4a,.aac,.ogg,.opus,.flac,.wma,.aiff,.aif"></div></div>

</section>

<aside class="panel side-panel"><div class="panel-head"><div><div class="step-label">02 / MIX</div><h2>اضبط مستوى الخلفية</h2><p class="panel-desc">ابدأ بمستوى خفيف حتى يبقى الصوت الأصلي واضحًا في المقدمة.</p></div></div>

<div class="mix-visual" aria-hidden="true">__WAVE__</div><div class="mix-caption">الصوت الأساسي <span style="color:#506d67">——</span> الخلفية المحيطة</div>

<div class="rule"></div><div class="mix-controls"><div class="slider-head"><span class="slider-title">مستوى صوت الخلفية</span><span class="slider-value" id="mixValue">12%</span></div><input class="range" type="range" id="mixLevel" name="mix_level" min="0" max="40" value="12"><div class="slider-help"><span>غير مسموع</span><span>خفيف — موصى به</span><span>أوضح</span></div>

<div class="format-row"><div class="format-label">صيغة التصدير<small>اختر الأنسب لاستخدامك</small></div><select class="format-select" name="format" id="format"><option value="ogg" selected>OGG · Opus · الحجم المناسب</option><option value="mp3">MP3 · حجم أصغر</option><option value="wav">WAV · جودة غير مضغوطة</option></select></div>

<div class="privacy-note"><svg viewBox="0 0 24 24"><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V7a4 4 0 0 1 8 0v3m-4 4v3"/></svg><span>المعالجة تتم على السيرفر باستخدام FFmpeg. لا يُرسل الملف الأصلي إلى Mixkit أو أي خادم خارجي.</span></div>

<button class="export-btn" id="exportButton" type="submit" disabled>امزج الصوت ونزّل الملف</button>

<div class="status" id="status" role="status" aria-live="polite"></div>

<div class="output" id="output"><div class="output-title">تم تجهيز المزيج — استمع أو نزّل الملف</div><audio id="resultAudio" controls></audio><a class="download-link" id="downloadLink" download>تنزيل المزيج</a></div>

<div class="howto"><h3>كيف يعمل؟</h3><div class="howto-row"><span class="num">١</span><span>اختر تسجيلك الأساسي من جهازك.</span></div><div class="howto-row"><span class="num">٢</span><span>حدد مؤثرًا أو ارفع خلفيتك الخاصة واضبط المستوى.</span></div><div class="howto-row"><span class="num">٣</span><span>استمع للنتيجة، ثم نزّلها بصيغة MP3 أو WAV.</span></div></div>

<div class="legal">مؤثرات الخلفية تُنزّل عند أول استخدام من <a href="https://mixkit.co/free-sound-effects/" target="_blank" rel="noopener">Mixkit</a> وتُخزّن مؤقتًا محليًا. تخضع لاستخدامات <a href="https://mixkit.co/license/#sfxFree" target="_blank" rel="noopener">رخصة المؤثرات المجانية</a> الخاصة بالمصدر.</div>

</aside></form>

<footer class="footer"><span>صوت ميكس · أداة محلية مجانية</span><span>أبقِ نافذة البرنامج مفتوحة أثناء المزج.</span></footer>

</div><audio id="scenePreview" preload="none"></audio>

<script>

const sourceFile=document.getElementById('sourceFile'), customFile=document.getElementById('customFile'), customWrap=document.getElementById('customWrap');

const exportButton=document.getElementById('exportButton'), statusBox=document.getElementById('status'), mixForm=document.getElementById('mixForm');

const dropZone=document.getElementById('dropZone'), sourcePreview=document.getElementById('sourcePreview');

let sourceUrl=null, resultUrl=null;

function setStatus(message,kind){statusBox.textContent=message;statusBox.className='status show '+kind}

function bytes(n){if(n<1024*1024)return (n/1024).toFixed(0)+' KB';return (n/1024/1024).toFixed(1)+' MB'}

function setSource(file){if(!file)return;document.getElementById('sourceName').textContent=file.name;document.getElementById('sourceSize').textContent=bytes(file.size);document.getElementById('sourceMeta').classList.add('show');if(sourceUrl)URL.revokeObjectURL(sourceUrl);sourceUrl=URL.createObjectURL(file);sourcePreview.src=sourceUrl;sourcePreview.classList.add('show');exportButton.disabled=false;statusBox.className='status';}

sourceFile.addEventListener('change',()=>setSource(sourceFile.files[0]));

for(const evt of ['dragenter','dragover'])dropZone.addEventListener(evt,e=>{e.preventDefault();dropZone.classList.add('drag')});

for(const evt of ['dragleave','drop'])dropZone.addEventListener(evt,e=>{e.preventDefault();dropZone.classList.remove('drag')});

dropZone.addEventListener('drop',e=>{const file=e.dataTransfer.files[0];if(file){const dt=new DataTransfer();dt.items.add(file);sourceFile.files=dt.files;setSource(file)}});

document.querySelectorAll('input[name="background"]').forEach(r=>r.addEventListener('change',()=>{customWrap.classList.toggle('show',r.value==='custom'&&r.checked);statusBox.className='status'}));

const slider=document.getElementById('mixLevel'),mixValue=document.getElementById('mixValue');

function updateSlider(){const n=Number(slider.value);mixValue.textContent=n+'%';slider.style.background=\`linear-gradient(90deg,#76e0c0 0%,#76e0c0 ${n*2.5}%,#304547 ${n*2.5}%)\`}

slider.addEventListener('input',updateSlider);updateSlider();

const sceneAudio=document.getElementById('scenePreview');

document.querySelectorAll('[data-listen]').forEach(btn=>btn.addEventListener('click',async e=>{e.preventDefault();e.stopPropagation();const key=btn.dataset.listen;try{if(sceneAudio.dataset.current===key&&!sceneAudio.paused){sceneAudio.pause();return}sceneAudio.pause();sceneAudio.src='/sounds/'+encodeURIComponent(key);sceneAudio.dataset.current=key;await sceneAudio.play()}catch(err){setStatus('تعذر تشغيل العينة. تحقق من اتصال الإنترنت ثم أعد المحاولة.', 'error')}}));

sceneAudio.addEventListener('error',()=>setStatus('تعذر تحميل عينة الخلفية من Mixkit. تحقق من اتصال الإنترنت ثم أعد المحاولة.','error'));

mixForm.addEventListener('submit',async e=>{e.preventDefault();const file=sourceFile.files[0];if(!file){setStatus('اختر ملفًا صوتيًا أولًا.','error');return}if(file.size>300*1024*1024){setStatus('حجم الملف يتجاوز 300 ميغابايت.','error');return}const selected=document.querySelector('input[name="background"]:checked');if(selected?.value==='custom'&&!customFile.files[0]){setStatus('اختر ملف الخلفية الخاص بك أو حدد مشهدًا جاهزًا.','error');return}if(customFile.files[0]&&customFile.files[0].size>300*1024*1024){setStatus('حجم الخلفية يتجاوز 300 ميغابايت.','error');return}exportButton.disabled=true;exportButton.innerHTML='<span class="spinner"></span> جارٍ تجهيز المزيج على السيرفر…';document.getElementById('output').classList.remove('show');setStatus('قد يستغرق التصدير بعض الوقت للملفات الطويلة. لا تغلق البرنامج الآن.','busy');try{const form=new FormData(mixForm);const response=await fetch('/api/mix',{method:'POST',body:form});if(!response.ok){let msg='تعذر إتمام المزج.';try{msg=(await response.json()).error||msg}catch{}throw new Error(msg)}const blob=await response.blob();if(resultUrl)URL.revokeObjectURL(resultUrl);resultUrl=URL.createObjectURL(blob);const ext=document.getElementById('format').value;const link=document.getElementById('downloadLink');link.href=resultUrl;link.download='soundmix-output.'+ext;document.getElementById('resultAudio').src=resultUrl;document.getElementById('output').classList.add('show');setStatus('اكتمل المزج. يمكنك الاستماع أو حفظ الملف.','ok');link.click()}catch(err){setStatus(err.message||'حدث خطأ أثناء المزج.','error')}finally{exportButton.disabled=false;exportButton.textContent='امزج الصوت ونزّل الملف'}});

</script></body></html>'''





def make_page() -> bytes:

    wave = "".join(

        f'<span class="bar" style="--i:{i};height:{height}px"></span>'

        for i, height in enumerate([14, 22, 34, 19, 27, 43, 23, 16, 37, 24, 47, 29, 18, 35, 25, 42, 16, 31, 46, 20, 36, 24, 14, 40, 29, 44, 19, 32, 15, 38, 24, 46, 18, 34, 22, 41, 15, 29, 43, 20, 36, 24, 16, 45, 31, 19, 37, 26, 42, 15, 30, 22, 39, 17, 33, 45, 25, 14, 35, 21, 42, 28, 17, 36])

    )

    page = PAGE.replace("__SCENE_CARDS__", render_background_cards()).replace("__WAVE__", wave)

    return page.encode("utf-8")





def parse_multipart(content_type: str, body: bytes) -> dict[str, tuple[str | None, bytes]]:

    header = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("ascii", "replace")

    message = BytesParser(policy=email.policy.default).parsebytes(header + body)

    if not message.is_multipart():

        raise ValueError("لم تصل بيانات الملف بشكل صحيح. أعد المحاولة.")

    fields: dict[str, tuple[str | None, bytes]] = {}

    for part in message.iter_parts():

        if part.get_content_disposition() != "form-data":

            continue

        name = part.get_param("name", header="content-disposition")

        if not name:

            continue

        filename = part.get_filename()

        raw_payload = part.get_payload(decode=True)

        payload = raw_payload if isinstance(raw_payload, bytes) else b""

        if payload:

            fields[str(name)] = (str(filename) if filename else None, payload)

    return fields





def safe_suffix(filename: str | None, fallback: str = ".bin") -> str:

    if not filename:

        return fallback

    suffix = Path(urllib.parse.unquote(filename)).suffix.lower()

    if not re.fullmatch(r"\.[a-z0-9]{1,8}", suffix):

        return fallback

    return suffix





def validate_audio_extension(filename: str | None) -> str:

    suffix = safe_suffix(filename, "")

    if not suffix:

        raise ValueError("تعذر تحديد صيغة الملف الصوتي.")

    if suffix not in ALLOWED_AUDIO_EXTENSIONS:

        raise ValueError(f"صيغة الصوت غير مدعومة: {suffix}")

    return suffix





def mix_audio(

    source_path: Path,

    background_path: Path,

    output_path: Path,

    level: int,

    out_format: str,

    ffmpeg: str,

) -> None:

    """

    مزج الصوت الأساسي مع الخلفية.



    آخر ثانيتين من الناتج:

    - الصوت الأساسي يكون صامتًا.

    - الخلفية/الضوضاء تستمر وحدها لمدة ثانيتين.



    يدعم الإدخال OGG/OGA/OPUS وغيرها، ويُخرج OGG باستخدام Opus

    عند اختيار OGG.

    """

    gain = max(0, min(40, int(level))) / 100.0



    graph = (

        # الصوت الأساسي + إضافة صمت لمدة ثانيتين في النهاية.

        "[0:a:0]"

        "aresample=async=1:first_pts=0,"

        "aformat=sample_fmts=fltp,"

        "apad=pad_dur=2"

        "[main];"



        # الخلفية تتكرر وتستمر حتى نهاية الصوت الأساسي + الثانيتين.

        f"[1:a:0]"

        f"volume={gain:.2f},"

        "aresample=async=1:first_pts=0,"

        "aformat=sample_fmts=fltp"

        "[bg];"



        # duration=first لأن [main] أصبح طوله = مدة الصوت + ثانيتين.

        "[main][bg]"

        "amix="

        "inputs=2:"

        "duration=first:"

        "dropout_transition=0"

        "[mixed];"



        # حماية مستوى الخرج من clipping.

        "[mixed]"

        "alimiter=limit=0.97"

        "[out]"

    )



    background_name = (

        "الخلفية المرفوعة"

        if background_path.name.startswith("custom")

        else "مؤثر Mixkit"

    )



    comment = (

        "SoundMix local mix; "

        f"background={background_name}; "

        f"background level={level}%; "

        "tail=2s background only; "

        "source=Mixkit Sound Effects Free License where applicable"

    )



    command = [

        ffmpeg,

        "-hide_banner",

        "-nostdin",

        "-loglevel", "error",

        "-y",



        # يساعد FFmpeg مع OGG/Opus والملفات ذات البيانات الوصفية الكبيرة.

        "-probesize", "100M",

        "-analyzeduration", "100M",



        # الصوت الأساسي.

        "-i", str(source_path),



        # الخلفية تتكرر.

        "-stream_loop", "-1",

        "-i", str(background_path),



        "-filter_complex", graph,

        "-map", "[out]",

        "-map_metadata", "0",

        "-metadata", "comment=" + comment,

    ]



    if out_format == "ogg":

        # OGG container + Opus codec.

        command += [

            "-c:a", "libopus",

            "-b:a", "128k",

            "-vbr", "on",

            "-compression_level", "10",

            "-application", "audio",

        ]



    elif out_format == "mp3":

        command += [

            "-c:a", "libmp3lame",

            "-q:a", "2",

            "-id3v2_version", "3",

        ]



    elif out_format == "wav":

        command += [

            "-c:a", "pcm_s16le",

        ]



    else:

        raise ValueError(

            "صيغة التصدير غير مدعومة. اختر OGG أو MP3 أو WAV."

        )



    command += [

        "-max_muxing_queue_size", "4096",

        str(output_path),

    ]



    try:

        result = subprocess.run(

            command,

            stdout=subprocess.DEVNULL,

            stderr=subprocess.PIPE,

            timeout=7200,

            check=False,

        )

    except subprocess.TimeoutExpired as exc:

        raise RuntimeError(

            "انتهت مهلة التصدير. جرّب ملفًا أقصر."

        ) from exc



    details = (

        (result.stderr or b"")

        .decode("utf-8", "replace")

        .strip()

    )



    if (

        result.returncode == 0

        and output_path.is_file()

        and output_path.stat().st_size >= 512

    ):

        return



    lower_error = details.lower()



    if "matches no streams" in lower_error or "does not contain any stream" in lower_error:

        raise RuntimeError(

            "الملف لا يحتوي على مسار صوتي صالح.\n\n"

            f"تفاصيل FFmpeg:\n{details[-3000:]}"

        )



    if "invalid data found when processing input" in lower_error:

        raise RuntimeError(

            "تعذر على FFmpeg قراءة الملف الصوتي. "

            "قد يكون ملف OGG تالفًا أو أن محتواه لا يطابق امتداده.\n\n"

            f"تفاصيل FFmpeg:\n{details[-3000:]}"

        )



    if "unknown encoder 'libopus'" in lower_error or "encoder not found" in lower_error:

        raise RuntimeError(

            "نسخة FFmpeg الحالية لا تحتوي على ترميز Opus (libopus)، "

            "وهو مطلوب لإخراج OGG. ثبّت نسخة FFmpeg كاملة ثم أعد تشغيل البرنامج.\n\n"

            f"تفاصيل FFmpeg:\n{details[-2000:]}"

        )



    if "unknown encoder 'libmp3lame'" in lower_error and out_format == "mp3":

        raise RuntimeError(

            "نسخة FFmpeg لا تحتوي على ترميز MP3 (libmp3lame).\n\n"

            f"تفاصيل FFmpeg:\n{details[-2000:]}"

        )



    raise RuntimeError(

        "فشل FFmpeg في قراءة أو مزج الملف.\n\n"

        f"تفاصيل الخطأ:\n{details[-3000:]}"

    )



def json_error(handler: BaseHTTPRequestHandler, code: int, message: str) -> None:

    raw = json.dumps({"success": False, "error": message}, ensure_ascii=False).encode("utf-8")

    handler.send_response(code)

    handler.send_header("Content-Type", "application/json; charset=utf-8")

    handler.send_header("Content-Length", str(len(raw)))

    handler.send_header("Cache-Control", "no-store")

    handler.send_header("Access-Control-Allow-Origin", CORS_ORIGIN)

    handler.send_header("X-Content-Type-Options", "nosniff")

    handler.end_headers()

    try:
        handler.wfile.write(raw)
    except (BrokenPipeError, ConnectionResetError):
        pass





class SoundMixServer(ThreadingHTTPServer):

    ffmpeg_path: str | None





class SoundMixHandler(BaseHTTPRequestHandler):

    server_version = "SoundMixAPI/1.1"

    sys_version = ""

    protocol_version = "HTTP/1.1"



    @property

    def app_server(self) -> SoundMixServer:

        return self.server  # type: ignore[return-value]



    def log_message(self, format: str, *args: object) -> None:

        # Avoid printing uploaded filenames or form contents to the console.

        sys.stdout.write("[SoundMix] " + (format % args) + "\n")



    def _api_key_allowed(self) -> bool:
        """Validate Bearer API authentication for external API clients."""
        if not API_KEY:
            return False
        authorization = self.headers.get("Authorization", "")
        if not authorization.startswith("Bearer "):
            return False
        supplied = authorization[7:].strip()
        return bool(supplied) and hmac.compare_digest(supplied, API_KEY)

    def _same_origin_allowed(self) -> bool:
        """Allow the bundled web UI to call its own API without exposing the API key."""
        origin = self.headers.get("Origin", "").rstrip("/")
        if not origin:
            return False
        host = self.headers.get("Host", "")
        return origin in {f"http://{host}", f"https://{host}"}

    def _authorized(self) -> bool:
        # The bundled UI can always use its own API.
        if self._same_origin_allowed():
            return True
        # API key is optional. If configured, external clients must send it.
        if not API_KEY:
            return True
        return self._api_key_allowed()

    def _cors_origin(self) -> str:
        return CORS_ORIGIN

    def _send_text(self, status: int, body: str, content_type: str = "text/plain; charset=utf-8") -> None:

        raw = body.encode("utf-8")

        self.send_response(status)

        self.send_header("Content-Type", content_type)

        self.send_header("Content-Length", str(len(raw)))

        self.send_header("X-Content-Type-Options", "nosniff")

        self.send_header("Cache-Control", "no-store")

        self.end_headers()

        self.wfile.write(raw)



    def do_GET(self) -> None:
        route = urllib.parse.urlsplit(self.path).path

        if route == "/api/health":
            raw = json.dumps({
                "success": True,
                "service": "soundmix",
                "version": "1.1",
                "status": "online",
                "ffmpeg": bool(self.app_server.ffmpeg_path),
                "api_key_required": bool(API_KEY),
            }, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", self._cors_origin())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return


        if route == "/api":
            raw = json.dumps({
                "success": True,
                "service": "soundmix",
                "version": "1.1",
                "ui": "/",
                "health": "/api/health",
                "mix": {
                    "method": "POST",
                    "path": "/api/mix",
                    "content_type": "multipart/form-data",
                    "fields": {
                        "audio": "required audio file",
                        "background": "rain|traffic|market|street|neighborhood|custom",
                        "custom_background": "required only when background=custom",
                        "mix_level": "0..40 (default 12)",
                        "format": "ogg|mp3|wav (default ogg)"
                    },
                    "authorization": "Bearer API_KEY when SOUNDMIX_API_KEY is configured"
                }
            }, ensure_ascii=False, indent=2).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Access-Control-Allow-Origin", self._cors_origin())
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(raw)
            return

        if route == "/" or route == "/index.html":
            body = make_page()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if route.startswith("/sounds/"):
            key = route.split("/", 2)[-1]
            if key not in BACKGROUNDS:
                self._send_text(404, "Not found")
                return
            try:
                path = cached_sound(key)
                size = path.stat().st_size
                self.send_response(200)
                self.send_header("Content-Type", "audio/mpeg")
                self.send_header("Content-Length", str(size))
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Cache-Control", "private, max-age=86400")
                self.end_headers()
                with path.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile, length=128 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                pass
            except Exception as exc:
                self.log_error("sound download failed: %s", str(exc)[:250])
                self._send_text(502, "تعذر تنزيل المؤثر الصوتي من Mixkit.")
            return

        self._send_text(404, "Not found")

    def do_OPTIONS(self) -> None:
        route = urllib.parse.urlsplit(self.path).path
        if route != "/api/mix":
            self._send_text(404, "Not found")
            return
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", self._cors_origin())
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
        self.send_header("Access-Control-Max-Age", "86400")
        self.end_headers()

    def do_POST(self) -> None:
        if urllib.parse.urlsplit(self.path).path != "/api/mix":
            json_error(self, 404, "المسار غير موجود.")
            return

        if not self._authorized():
            json_error(self, 401, "API Key غير صالح. استخدم Authorization: Bearer YOUR_API_KEY.")
            return

        ffmpeg_path = self.app_server.ffmpeg_path

        if not ffmpeg_path:

            json_error(self, 503, "لم أجد FFmpeg. ثبّته ثم أعد تشغيل الأداة؛ راجع README_AR.md.")

            return

        try:

            length = int(self.headers.get("Content-Length", "0"))

        except ValueError:

            json_error(self, 411, "تعذر تحديد حجم الملف.")

            return

        if length <= 0 or length > MAX_BODY_BYTES:

            json_error(self, 413, "حجم الطلب كبير جدًا. الحد الأقصى لكل ملف 300 ميغابايت.")

            return

        content_type = self.headers.get("Content-Type", "")

        if "multipart/form-data" not in content_type.lower():

            json_error(self, 415, "صيغة الرفع غير مدعومة.")

            return

        try:

            fields = parse_multipart(content_type, self.rfile.read(length))

            source_file = fields.get("audio")

            if not source_file or not source_file[1]:

                raise ValueError("اختر ملف الصوت الأساسي أولًا.")

            validate_audio_extension(source_file[0])

            if len(source_file[1]) > MAX_FILE_BYTES:

                raise ValueError("حجم الصوت الأساسي يتجاوز 300 ميغابايت.")

            background_field = fields.get("background", (None, b"rain"))[1].decode("utf-8", "replace").strip()

            try:

                level = int(fields.get("mix_level", (None, b"12"))[1].decode("ascii", "ignore"))

            except ValueError as exc:

                raise ValueError("قيمة مستوى الخلفية غير صالحة.") from exc

            if not 0 <= level <= 40:

                raise ValueError("مستوى الخلفية يجب أن يكون بين 0 و40 بالمئة.")

            out_format = fields.get("format", (None, b"ogg"))[1].decode("ascii", "ignore").lower()

            if out_format not in {"ogg", "mp3", "wav"}:

                raise ValueError("اختر OGG أو MP3 أو WAV للتصدير.")

            if background_field == "custom":

                custom = fields.get("custom_background")

                if not custom or not custom[1]:

                    raise ValueError("اختر ملف الخلفية الخاص بك.")

                if len(custom[1]) > MAX_FILE_BYTES:

                    raise ValueError("حجم الخلفية يتجاوز 300 ميغابايت.")

                validate_audio_extension(custom[0])

            elif background_field not in BACKGROUNDS:

                raise ValueError("اختر خلفية من القائمة.")



            with tempfile.TemporaryDirectory(prefix="soundmix-") as temp_dir:

                temp = Path(temp_dir)

                source_path = temp / ("source" + safe_suffix(source_file[0]))

                source_path.write_bytes(source_file[1])

                if background_field == "custom":

                    background_path = temp / ("custom" + safe_suffix(fields["custom_background"][0]))

                    background_path.write_bytes(fields["custom_background"][1])

                else:

                    background_path = cached_sound(background_field)

                output_path = temp / ("soundmix-output." + out_format)

                mix_audio(source_path, background_path, output_path, level, out_format, ffmpeg_path)

                output_size = output_path.stat().st_size

                if output_size > 1024 * 1024 * 1024:

                    raise RuntimeError("حجم الملف الناتج أكبر من 1 غيغابايت؛ اختر MP3 أو قلّل مدة التسجيل.")

                mime = "audio/ogg" if out_format == "ogg" else ("audio/mpeg" if out_format == "mp3" else "audio/wav")

                self.send_response(200)

                self.send_header("Content-Type", mime)

                self.send_header("Content-Length", str(output_size))

                self.send_header("Content-Disposition", f'attachment; filename="soundmix-output.{out_format}"')

                self.send_header("X-Content-Type-Options", "nosniff")

                self.send_header("Cache-Control", "no-store")

                self.send_header("Access-Control-Allow-Origin", self._cors_origin())

                self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")

                self.end_headers()

                with output_path.open("rb") as stream:

                    shutil.copyfileobj(stream, self.wfile, length=256 * 1024)

        except (BrokenPipeError, ConnectionResetError):

            pass

        except ValueError as exc:

            json_error(self, 400, str(exc))

        except RuntimeError as exc:

            json_error(self, 422, str(exc))

        except urllib.error.URLError as exc:

            self.log_error("sound source connection failed: %s", str(exc)[:250])

            json_error(self, 502, "تعذر الاتصال بمكتبة المؤثرات لأول مرة. تحقق من الإنترنت ثم أعد المحاولة.")

        except Exception as exc:

            self.log_error("mix failed: %s", str(exc)[:400])

            json_error(self, 500, "حدث خطأ غير متوقع أثناء المزج. تحقق من صيغة الصوت ثم حاول مرة أخرى.")





def start_server(port: int, open_browser: bool) -> None:

    ffmpeg = find_ffmpeg()

    if ffmpeg:

        try:

            check = subprocess.run([ffmpeg, "-version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)

            if check.returncode != 0:

                ffmpeg = None

        except Exception:

            ffmpeg = None

    try:

        server = SoundMixServer((HOST, port), SoundMixHandler)

    except OSError as exc:

        raise SystemExit(f"تعذر فتح المنفذ {port}: {exc}. جرّب خيار --port.") from exc

    server.daemon_threads = True

    server.ffmpeg_path = ffmpeg  # type: ignore[attr-defined]

    display_host = "127.0.0.1" if HOST in {"0.0.0.0", "::"} else HOST
    url = f"http://{display_host}:{server.server_port}/"

    print(f"\n{APP_NAME} API يعمل على: {url}")
    print(f"API endpoint: http://{display_host}:{server.server_port}/api/mix")
    print("المعالجة تتم على السيرفر على هذا السيرفر. أوقف الخدمة بـ Ctrl+C.\n")

    if not API_KEY:
        print("تنبيه: SOUNDMIX_API_KEY غير مضبوط؛ الـ API متاح حاليًا بدون مصادقة. أضف المفتاح في Render لحمايته.\n")

    if not ffmpeg:

        print("تنبيه: FFmpeg غير مثبت. ثبّته قبل التصدير (التعليمات في README_AR.md).\n")

    if open_browser:

        threading.Timer(0.45, lambda: webbrowser.open_new_tab(url)).start()

    try:

        server.serve_forever(poll_interval=0.4)

    except KeyboardInterrupt:

        print("\nتم إيقاف صوت ميكس.")

    finally:

        server.server_close()





def main() -> None:

    parser = argparse.ArgumentParser(description="صوت ميكس — API لمزج الصوت مع خلفية")

    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help=f"منفذ الواجهة المحلية (الافتراضي: {DEFAULT_PORT})")

    parser.add_argument("--no-browser", action="store_true", help="لا تفتح المتصفح تلقائيًا")

    args = parser.parse_args()

    if not 1024 <= args.port <= 65535:

        parser.error("يجب أن يكون المنفذ بين 1024 و65535.")

    start_server(args.port, not args.no_browser)





if __name__ == "__main__":

    main()
