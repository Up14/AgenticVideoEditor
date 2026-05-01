"""
Utility functions for a YouTube caption pipeline.

NOTE:
- This file assumes CLEAN caption tracks (manual / regional).
- No ASR de-duplication or auto-caption heuristics are applied here.
"""

import re
import json
import html
from typing import List, Dict, Any

# =========================================================
# TIME UTILITIES
# =========================================================

def _timestamp_to_seconds(timestamp: str) -> float:
    """
    Converts a timestamp string (HH:MM:SS.ms or HH:MM:SS,ms) to seconds.
    """
    ts = timestamp.replace(",", ".")
    parts = ts.split(":")

    if len(parts) == 3:
        h, m, s_ms = parts
    elif len(parts) == 2:
        h = 0
        m, s_ms = parts
    else:
        raise ValueError(f"Invalid timestamp format: {timestamp}")

    if "." in s_ms:
        s, ms = s_ms.split(".", 1)
    else:
        s, ms = s_ms, "0"

    return (
        int(h) * 3600
        + int(m) * 60
        + int(s)
        + int(ms.ljust(3, "0")[:3]) / 1000
    )


def seconds_to_timestamp(seconds: float) -> str:
    """
    Converts seconds to VTT-style timestamp HH:MM:SS.mmm
    """
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def _clean_vtt_timestamp(ts: str) -> str:
    """
    Removes cue settings from VTT timestamps.
    Example:
      '00:00:01.000 align:start position:0%' → '00:00:01.000'
    """
    return ts.strip().split(" ")[0]


# =========================================================
# TEXT NORMALIZATION
# =========================================================

def _normalize_text(text: str) -> str:
    """
    Basic caption text cleanup:
    - HTML unescape
    - Remove tags
    - Normalize whitespace
    """
    text = html.unescape(text)
    text = re.sub(r"<[^>]+>", "", text)          # remove HTML tags
    text = re.sub(r">>\s*", "", text)            # remove speaker arrows
    text = re.sub(r"\s+", " ", text).strip()     # normalize spaces
    return text


# =========================================================
# PARSERS
# =========================================================

def parse_vtt_to_text(vtt_content: str) -> List[Dict[str, Any]]:
    """
    Parses a VTT caption file into structured caption data.
    """
    captions = []
    lines = vtt_content.strip().splitlines()
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
                    "start": start,
                    "end": end,
                    "text": _normalize_text(" ".join(text_lines))
                })

        except Exception:
            continue

    return captions


def parse_srt_to_text(srt_content: str) -> List[Dict[str, Any]]:
    """
    Parses an SRT caption file into structured caption data.
    """
    captions = []
    blocks = srt_content.strip().split("\n\n")

    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue

        try:
            time_line = lines[1]
            start, end = [
                t.strip().replace(",", ".")
                for t in time_line.split("-->")
            ]

            captions.append({
                "start": start,
                "end": end,
                "text": _normalize_text(" ".join(lines[2:]))
            })

        except Exception:
            continue

    return captions


# =========================================================
# FORMATTERS
# =========================================================

def format_captions_for_display(caption_data: List[Dict[str, Any]]) -> str:
    """
    Human-readable caption display format.
    """
    return "\n".join(
        f"[{c['start']}] --> [{c['end']}]\n{c['text']}\n"
        for c in caption_data
    )


def convert_to_srt(caption_data: List[Dict[str, Any]]) -> str:
    """
    Converts captions to SRT format.
    """
    output = []

    for i, c in enumerate(caption_data, start=1):
        output.extend([
            str(i),
            f"{c['start'].replace('.', ',')} --> {c['end'].replace('.', ',')}",
            c["text"],
            ""
        ])

    return "\n".join(output)


def convert_to_vtt(caption_data: List[Dict[str, Any]]) -> str:
    """
    Converts captions to VTT format.
    """
    body = "\n\n".join(
        f"{c['start']} --> {c['end']}\n{c['text']}"
        for c in caption_data
    )
    return "WEBVTT\n\n" + body


def convert_to_txt(caption_data: List[Dict[str, Any]]) -> str:
    """
    Converts captions to plain text.
    """
    return "\n".join(c["text"] for c in caption_data)


def convert_to_json(
    caption_data: List[Dict[str, Any]],
    source: str,
    language: str
) -> str:
    """
    Converts captions to JSON.
    """
    return json.dumps(
        {
            "source": source,
            "language": language,
            "caption_count": len(caption_data),
            "captions": caption_data
        },
        indent=2,
        ensure_ascii=False
    )


# =========================================================
# FORMAT DETECTION
# =========================================================

def detect_format(content: str) -> str:
    """
    Detects caption format from raw content.
    """
    content = content.lstrip()

    if content.startswith("WEBVTT"):
        return "vtt"

    if re.search(r"\d{2}:\d{2}:\d{2},\d{3}\s+-->", content):
        return "srt"

    return "vtt"
