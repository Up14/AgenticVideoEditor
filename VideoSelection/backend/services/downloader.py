"""
Video downloader service — wraps yt-dlp to download YouTube videos.
"""

import os
import uuid
import logging
from typing import Optional, Dict, Any

import yt_dlp

logger = logging.getLogger(__name__)

# Base directory for all downloaded media
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)


def _get_video_dir(video_id: str) -> str:
    """Returns the directory for a specific video, creating it if needed."""
    path = os.path.join(MEDIA_DIR, video_id)
    os.makedirs(path, exist_ok=True)
    return path


def download_video(url: str, quality: int = 720) -> Dict[str, Any]:
    """
    Downloads a YouTube video using yt-dlp.

    Args:
        url: YouTube video URL.
        quality: Maximum video height (360, 480, 720, 1080).

    Returns:
        Dict with video_id, file_path, title, duration.
    """
    video_id = uuid.uuid4().hex[:12]
    video_dir = _get_video_dir(video_id)
    output_path = os.path.join(video_dir, "video.mp4")

    ydl_opts = {
        "format": f"bestvideo[height<={quality}]+bestaudio[ext=m4a]/bestvideo+bestaudio",
        "merge_output_format": "mp4",
        "outtmpl": output_path,
        "no_playlist": True,
        "force_overwrites": True,
        "quiet": True,
        "no_warnings": True,
    }

    logger.info("Downloading video: %s (quality=%dp)", url, quality)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "Untitled")
    duration = info.get("duration", 0)

    logger.info("Download complete: %s (%.1fs)", title, duration)

    return {
        "video_id": video_id,
        "file_path": output_path,
        "title": title,
        "duration": float(duration),
    }


def get_video_path(video_id: str) -> Optional[str]:
    """Returns the file path for a downloaded video, or None if not found."""
    path = os.path.join(MEDIA_DIR, video_id, "video.mp4")
    return path if os.path.exists(path) else None
