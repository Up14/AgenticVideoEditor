"""
frame_extractor.py
──────────────────
Extracts frames from a local MP4 file at a configurable sample rate.

Public API
----------
extract_frames(video_path, sample_fps) -> generator of FrameData
get_video_meta(video_path)             -> dict of video metadata
"""

from __future__ import annotations
import cv2
import numpy as np
from dataclasses import dataclass
from typing import Generator


@dataclass
class FrameData:
    index: int          # sequential frame number (0-based, among sampled frames)
    timestamp: float    # position in seconds
    bgr: np.ndarray     # raw BGR image array


def get_video_meta(video_path: str) -> dict:
    """Return basic metadata about the video file."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    native_fps   = cap.get(cv2.CAP_PROP_FPS) or 30.0
    width        = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height       = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_sec = total_frames / native_fps if native_fps > 0 else 0.0
    cap.release()

    return {
        "total_frames":  total_frames,
        "native_fps":    round(native_fps, 2),
        "width":         width,
        "height":        height,
        "duration_sec":  round(duration_sec, 2),
    }


def extract_frames(
    video_path: str,
    sample_fps: float = 5.0,
) -> Generator[FrameData, None, None]:
    """
    Yield sampled frames from *video_path* at *sample_fps* frames per second.

    Parameters
    ----------
    video_path  : path to the MP4 file
    sample_fps  : how many frames per second to sample (e.g. 5 → one frame
                  every 200 ms).  Capped to the video's native FPS.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError(f"Cannot open video: {video_path}")

    native_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    sample_fps = min(sample_fps, native_fps)

    # How many native frames to skip between each sampled frame
    frame_step = max(1, int(round(native_fps / sample_fps)))

    frame_idx       = 0   # native frame counter
    sampled_count   = 0   # sampled frame counter

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % frame_step == 0:
                timestamp = frame_idx / native_fps
                yield FrameData(
                    index     = sampled_count,
                    timestamp = round(timestamp, 4),
                    bgr       = frame,
                )
                sampled_count += 1

            frame_idx += 1
    finally:
        cap.release()
