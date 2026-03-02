"""
Video trimmer service — uses ffmpeg to cut video clips and slice captions.
"""

import os
import json
import logging
import subprocess
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")


def seconds_to_timestamp(seconds: float) -> str:
    """Converts float seconds to ffmpeg-compatible HH:MM:SS.mmm format."""
    seconds = max(0.0, seconds)
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}"


def trim_video(video_id: str, start: float, end: float, suffix: str = "") -> str:
    """
    Trims a video using ffmpeg.

    Args:
        video_id: ID of the source video.
        start: Start time in seconds.
        end: End time in seconds.
        suffix: Optional suffix for the output filename (e.g., '_seg1').

    Returns:
        Path to the trimmed clip file.

    Raises:
        FileNotFoundError: If source video doesn't exist.
        RuntimeError: If ffmpeg fails.
    """
    source_path = os.path.join(MEDIA_DIR, video_id, "video.mp4")
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source video not found: {video_id}")

    # Create clips directory
    clips_dir = os.path.join(MEDIA_DIR, video_id, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    clip_filename = f"clip_{start:.1f}_{end:.1f}{suffix}.mp4"
    clip_path = os.path.join(clips_dir, clip_filename)

    # If clip already exists, return it
    if os.path.exists(clip_path):
        return clip_path

    cmd = [
        "ffmpeg",
        "-y",                          # overwrite
        "-ss", seconds_to_timestamp(start),
        "-to", seconds_to_timestamp(end),
        "-i", source_path,
        "-c:v", "libx264",
        "-c:a", "aac",
        "-avoid_negative_ts", "1",
        "-movflags", "+faststart",      # web-optimized
        clip_path,
    ]

    logger.info("Trimming video: %s [%.1f → %.1f]", video_id, start, end)

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if result.returncode != 0:
        logger.error("ffmpeg failed: %s", result.stderr[-500:] if result.stderr else "unknown")
        raise RuntimeError(f"ffmpeg trim failed: {result.stderr[-200:] if result.stderr else 'unknown'}")

    logger.info("Trim complete: %s", clip_path)
    return clip_path


def slice_captions(
    captions: List[Dict[str, Any]],
    start: float,
    end: float,
) -> List[Dict[str, Any]]:
    """
    Slices captions to a time range and re-offsets timestamps to start at 0.

    Args:
        captions: Full list of caption dicts with start/end/text.
        start: Selection start time in seconds.
        end: Selection end time in seconds.

    Returns:
        List of caption dicts with re-timed timestamps.
    """
    trimmed = []
    for cap in captions:
        # Skip captions entirely outside the range
        if cap["end"] <= start or cap["start"] >= end:
            continue

        trimmed.append({
            "start": round(max(0, cap["start"] - start), 3),
            "end": round(min(end - start, cap["end"] - start), 3),
            "text": cap["text"],
        })

    return trimmed


def save_trimmed_captions(
    video_id: str,
    captions: List[Dict],
    start: float,
    end: float,
    suffix: str = "",
) -> str:
    """Saves trimmed captions as a JSON file and returns the path."""
    clips_dir = os.path.join(MEDIA_DIR, video_id, "clips")
    os.makedirs(clips_dir, exist_ok=True)

    filename = f"captions_{start:.1f}_{end:.1f}{suffix}.json"
    path = os.path.join(clips_dir, filename)

    with open(path, "w", encoding="utf-8") as f:
        json.dump({
            "original_start": start,
            "original_end": end,
            "duration": round(end - start, 3),
            "caption_count": len(captions),
            "captions": captions,
        }, f, indent=2, ensure_ascii=False)

    return path
