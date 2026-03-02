"""
Export router — trims video and slices captions for the selected region.
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from models.schemas import ExportRequest, ExportResponse
from services.trimmer import trim_video, slice_captions, save_trimmed_captions
from services.caption_service import get_captions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["export"])

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")


@router.post("/export", response_model=ExportResponse)
async def export_clip(req: ExportRequest):
    """
    Trims the video to the selected region and produces
    a trimmed captions file.
    """
    if req.start >= req.end:
        raise HTTPException(status_code=400, detail="Start must be before end")

    try:
        # Trim video
        clip_path = trim_video(req.video_id, req.start, req.end)

        # Slice captions
        caption_data = get_captions(req.video_id)
        if caption_data and caption_data.get("captions"):
            trimmed_caps = slice_captions(caption_data["captions"], req.start, req.end)
        else:
            trimmed_caps = []

        captions_path = save_trimmed_captions(
            req.video_id, trimmed_caps, req.start, req.end
        )

        # Build response URLs
        clip_url = f"/api/download/clip/{req.video_id}/{os.path.basename(clip_path)}"
        captions_url = f"/api/download/captions/{req.video_id}/{os.path.basename(captions_path)}"

        return ExportResponse(
            clip_url=clip_url,
            captions_url=captions_url,
            start=req.start,
            end=req.end,
            duration=round(req.end - req.start, 3),
            caption_count=len(trimmed_caps),
        )

    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.exception("Export failed for %s", req.video_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/download/clip/{video_id}/{filename}")
async def download_clip(video_id: str, filename: str):
    """Serves a trimmed clip for download."""
    path = os.path.join(MEDIA_DIR, video_id, "clips", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Clip not found")
    return FileResponse(path, media_type="video/mp4", filename=filename)


@router.get("/download/captions/{video_id}/{filename}")
async def download_captions(video_id: str, filename: str):
    """Serves trimmed captions for download."""
    path = os.path.join(MEDIA_DIR, video_id, "clips", filename)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Captions file not found")
    return FileResponse(path, media_type="application/json", filename=filename)
