"""
Video router — serves downloaded video files for the HTML5 video player.
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from services.downloader import get_video_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["video"])


@router.get("/video/{video_id}")
async def stream_video(video_id: str):
    """Serves the downloaded video file."""
    path = get_video_path(video_id)
    if not path:
        raise HTTPException(status_code=404, detail="Video not found")

    return FileResponse(
        path,
        media_type="video/mp4",
        filename=f"{video_id}.mp4",
    )
