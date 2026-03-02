"""
Captions router — serves parsed caption data.
"""

import logging
from fastapi import APIRouter, HTTPException

from models.schemas import CaptionsResponse, Caption
from services.caption_service import get_captions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["captions"])


@router.get("/captions/{video_id}", response_model=CaptionsResponse)
async def get_video_captions(video_id: str):
    """Returns parsed captions for a processed video."""
    data = get_captions(video_id)
    if not data:
        raise HTTPException(status_code=404, detail="Captions not found")

    return CaptionsResponse(
        video_id=video_id,
        source=data.get("source"),
        language=data.get("language"),
        captions=[
            Caption(start=c["start"], end=c["end"], text=c["text"])
            for c in data["captions"]
        ],
    )
