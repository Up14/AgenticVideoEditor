"""
Video downloader service — wraps yt-dlp to download YouTube videos.

Automatically detects whether ffmpeg is available:
- With ffmpeg: downloads best separate video + audio and merges them.
- Without ffmpeg: downloads best single progressive stream (no merging).
"""

import os
import glob
import uuid
import shutil
import logging
from typing import Optional, Dict, Any

import yt_dlp

logger = logging.getLogger(__name__)

# Base directory for all downloaded media
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)


def _has_ffmpeg() -> bool:
    """Checks whether ffmpeg is available on the system PATH."""
    return shutil.which("ffmpeg") is not None


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
    output_template = os.path.join(video_dir, "video.%(ext)s")

    ffmpeg_available = _has_ffmpeg()

    if ffmpeg_available:
        # Merge best separate streams (requires ffmpeg)
        fmt = f"bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
        ydl_opts = {
            "format": fmt,
            "merge_output_format": "mp4",
            "outtmpl": output_template,
            "no_playlist": True,
            "force_overwrites": True,
            "quiet": True,
            "no_warnings": True,
        }
        logger.info("Downloading video (merge mode, ffmpeg available): %s (quality=%dp)", url, quality)
    else:
        # Download single progressive stream — no ffmpeg needed
        fmt = f"best[height<={quality}][ext=mp4]/best[ext=mp4]/best[height<={quality}]/best"
        ydl_opts = {
            "format": fmt,
            "outtmpl": output_template,
            "no_playlist": True,
            "force_overwrites": True,
            "quiet": True,
            "no_warnings": True,
        }
        logger.info("Downloading video (single-stream mode, ffmpeg NOT found): %s (quality=%dp)", url, quality)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    title = info.get("title", "Untitled")
    duration = info.get("duration", 0)

    # Find the actual downloaded file (extension may vary)
    downloaded_files = glob.glob(os.path.join(video_dir, "video.*"))
    downloaded_files = [f for f in downloaded_files if not f.endswith(".part")]

    if not downloaded_files:
        raise RuntimeError("Download completed but no video file was found")

    actual_path = downloaded_files[0]

    # Rename to video.mp4 if needed (for consistent serving)
    final_path = os.path.join(video_dir, "video.mp4")
    if actual_path != final_path:
        os.rename(actual_path, final_path)

    logger.info("Download complete: %s (%.1fs)", title, duration)

    return {
        "video_id": video_id,
        "file_path": final_path,
        "title": title,
        "duration": float(duration),
    }


def get_video_path(video_id: str) -> Optional[str]:
    """Returns the file path for a downloaded video, or None if not found."""
    path = os.path.join(MEDIA_DIR, video_id, "video.mp4")
    return path if os.path.exists(path) else None
