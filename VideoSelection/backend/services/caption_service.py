"""
Caption extraction service — downloads and parses YouTube captions.

Reuses the parsing logic from ExistingCode/YtCaptionDownloader but
reimplemented as a clean service without Streamlit dependencies.
"""

import os
import re
import html
import json
import shutil
import logging
import tempfile
from typing import List, Dict, Any, Optional

import yt_dlp

from services.cookie_service import get_smart_cookie_opts, cleanup_shadow_profile

logger = logging.getLogger(__name__)

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")


# ── Timestamp Utilities ──

def _timestamp_to_seconds(ts: str) -> float:
    """Converts 'HH:MM:SS.ms' or 'HH:MM:SS,ms' to float seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    if len(parts) == 3:
        h, m, s_ms = parts
    elif len(parts) == 2:
        h = 0
        m, s_ms = parts
    else:
        raise ValueError(f"Invalid timestamp: {ts}")

    if "." in str(s_ms):
        s, ms = str(s_ms).split(".", 1)
    else:
        s, ms = s_ms, "0"

    return int(h) * 3600 + int(m) * 60 + int(s) + int(str(ms).ljust(3, "0")[:3]) / 1000


def _clean_vtt_timestamp(ts: str) -> str:
    """Removes cue settings from VTT timestamps."""
    return ts.strip().split(" ")[0]


def _normalize_text(text: str) -> str:
    """Cleans caption text: un-escapes HTML, removes tags, normalizes spaces."""
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r">>\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


# ── Format Detection ──

def _detect_format(content: str) -> str:
    content = content.lstrip()
    if content.startswith("WEBVTT"):
        return "vtt"
    if re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->", content):
        return "srt"
    return "vtt"


# ── Parsers ──

def _parse_vtt(content: str) -> List[Dict[str, Any]]:
    captions = []
    lines = content.strip().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if "-->" not in line:
            continue
        try:
            start_raw, end_raw = line.split("-->")
            start = _clean_vtt_timestamp(start_raw).replace(",", ".")
            end = _clean_vtt_timestamp(end_raw).replace(",", ".")
            text_lines = []
            while i < len(lines) and lines[i].strip():
                text_lines.append(lines[i].strip())
                i += 1
            if text_lines:
                captions.append({
                    "start": _timestamp_to_seconds(start),
                    "end": _timestamp_to_seconds(end),
                    "text": _normalize_text(" ".join(text_lines)),
                })
        except Exception:
            continue
    return captions


def _parse_srt(content: str) -> List[Dict[str, Any]]:
    captions = []
    blocks = content.strip().split("\n\n")
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            start, end = [t.strip().replace(",", ".") for t in lines[1].split("-->")]
            captions.append({
                "start": _timestamp_to_seconds(start),
                "end": _timestamp_to_seconds(end),
                "text": _normalize_text(" ".join(lines[2:])),
            })
        except Exception:
            continue
    return captions


# ── Deduplication (for auto-generated captions) ──

def _deduplicate_captions(captions: List[Dict]) -> List[Dict]:
    """Merges exact duplicates and prefix extensions, similar to caption_processor.py."""
    if not captions:
        return []

    output = [captions[0].copy()]
    for i in range(1, len(captions)):
        curr = captions[i]
        prev = output[-1]

        # Exact duplicate — extend end time
        if curr["text"] == prev["text"]:
            prev["end"] = curr["end"]
            continue

        # Prefix extension — extract only the new part
        if curr["text"].startswith(prev["text"]):
            remaining = curr["text"][len(prev["text"]):].strip()
            if not remaining:
                prev["end"] = curr["end"]
                continue
            output.append({"start": curr["start"], "end": curr["end"], "text": remaining})
            continue

        # New caption
        output.append(curr.copy())

    return output


# ── Caption Track Selection ──

def _find_english_track(metadata: Dict) -> Optional[Dict]:
    """Finds the best English caption track with priority: manual > auto > translated."""
    subtitles = metadata.get("subtitles", {})
    auto_caps = metadata.get("automatic_captions", {})

    # 1. Manual English
    for lang in sorted(k for k in subtitles if k.lower() == "en" or k.lower().startswith("en-")):
        tracks = subtitles.get(lang, [])
        for ext in ("vtt", "srt"):
            for t in tracks:
                if t.get("ext") == ext and t.get("url"):
                    return {"url": t["url"], "ext": ext, "source": "manual", "language": lang}
        if tracks and tracks[0].get("url"):
            return {"url": tracks[0]["url"], "ext": tracks[0].get("ext", "vtt"),
                    "source": "manual", "language": lang}

    # 2. Auto-generated English
    for lang in sorted(k for k in auto_caps if k.lower() == "en" or k.lower().startswith("en-")):
        tracks = auto_caps.get(lang, [])
        for ext in ("vtt", "srt"):
            for t in tracks:
                if t.get("ext") == ext and t.get("url"):
                    return {"url": t["url"], "ext": ext, "source": "auto", "language": lang}
        if tracks and tracks[0].get("url"):
            return {"url": tracks[0]["url"], "ext": tracks[0].get("ext", "vtt"),
                    "source": "auto", "language": lang}

    # 3. Auto-translated English
    for lang in sorted(k for k in auto_caps if k.lower().endswith("-en")):
        tracks = auto_caps.get(lang, [])
        for t in tracks:
            if t.get("ext") == "vtt" and t.get("url"):
                return {"url": t["url"], "ext": "vtt", "source": "auto-translated", "language": "en"}
        if tracks and tracks[0].get("url"):
            return {"url": tracks[0]["url"], "ext": tracks[0].get("ext", "vtt"),
                    "source": "auto-translated", "language": "en"}

    return None


def _get_cookie_opts() -> Dict[str, Any]:
    """Returns yt-dlp cookie options from environment variables."""
    opts = {}
    cookie_path = os.getenv("YOUTUBE_COOKIES_PATH")
    cookie_browser = os.getenv("YOUTUBE_COOKIES_BROWSER")

    if cookie_path and os.path.exists(cookie_path):
        opts["cookiefile"] = cookie_path
    elif cookie_browser:
        opts["cookiesfrombrowser"] = (cookie_browser,)
    return opts


# ── Public API ──

def extract_captions(url: str, video_id: str) -> Dict[str, Any]:
    """
    Downloads and parses captions for a YouTube video.

    Args:
        url: YouTube video URL.
        video_id: ID for storing caption files.

    Returns:
        Dict with captions list, source, language.
    """
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        **get_smart_cookie_opts(),
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            metadata = ydl.extract_info(url, download=False)
            track = _find_english_track(metadata)

            if not track:
                logger.warning("No English captions found for %s", url)
                return {"captions": [], "source": None, "language": None}

            # Download caption file to temp
            tmp_dir = tempfile.mkdtemp()
            try:
                tmp_file = os.path.join(tmp_dir, f"captions.{track['ext']}")
                response = ydl.urlopen(track["url"])
                with open(tmp_file, "wb") as f:
                    shutil.copyfileobj(response, f)

                with open(tmp_file, "r", encoding="utf-8", errors="replace") as f:
                    content = f.read()
            finally:
                shutil.rmtree(tmp_dir, ignore_errors=True)
    finally:
        cleanup_shadow_profile(ydl_opts)

    # Parse
    fmt = _detect_format(content)
    captions = _parse_srt(content) if fmt == "srt" else _parse_vtt(content)

    # Deduplicate auto-generated captions
    if track["source"] in ("auto", "auto-translated"):
        captions = _deduplicate_captions(captions)

    # Save captions JSON to media dir
    captions_path = os.path.join(MEDIA_DIR, video_id, "captions.json")
    os.makedirs(os.path.dirname(captions_path), exist_ok=True)
    with open(captions_path, "w", encoding="utf-8") as f:
        json.dump({
            "source": track["source"],
            "language": track["language"],
            "captions": captions,
        }, f, indent=2, ensure_ascii=False)

    logger.info("Extracted %d captions (source=%s, lang=%s)", len(captions), track["source"], track["language"])

    return {
        "captions": captions,
        "source": track["source"],
        "language": track["language"],
    }


def get_captions(video_id: str) -> Optional[Dict]:
    """Loads saved captions for a video."""
    path = os.path.join(MEDIA_DIR, video_id, "captions.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
