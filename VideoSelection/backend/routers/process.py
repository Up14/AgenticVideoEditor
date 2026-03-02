"""
Process router — handles YouTube URL processing (download video + extract captions).
"""

import logging
from fastapi import APIRouter, HTTPException

from models.schemas import ProcessRequest, ProcessResponse, Caption
from services.downloader import download_video
from services.caption_service import extract_captions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["process"])


@router.post("/process", response_model=ProcessResponse)
async def process_youtube_url(req: ProcessRequest):
    """
    Downloads a YouTube video and extracts its captions.
    Returns video metadata, captions, and a URL to stream the video.
    """
    try:
        # Step 1: Download video
        video_info = download_video(req.url, req.quality)
        video_id = video_info["video_id"]

        # Step 2: Extract captions
        caption_info = extract_captions(req.url, video_id)

        # Build response
        captions = [
            Caption(start=c["start"], end=c["end"], text=c["text"])
            for c in caption_info["captions"]
        ]

        return ProcessResponse(
            video_id=video_id,
            title=video_info["title"],
            duration=video_info["duration"],
            video_url=f"/api/video/{video_id}",
            captions=captions,
            source=caption_info.get("source"),
            language=caption_info.get("language"),
        )

    except Exception as e:
        logger.exception("Failed to process URL: %s", req.url)
        raise HTTPException(status_code=500, detail=str(e))
