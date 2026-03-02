"""
Pydantic models for API request/response schemas.
"""

from pydantic import BaseModel
from typing import List, Optional


# ── Request Models ──

class ProcessRequest(BaseModel):
    """Request body for processing a YouTube URL."""
    url: str
    quality: int = 720  # max video height: 360, 480, 720, 1080


class ExportRequest(BaseModel):
    """Request body for exporting a trimmed clip."""
    video_id: str
    start: float  # seconds
    end: float    # seconds
    format: str = "mp4"


# ── Caption Models ──

class Caption(BaseModel):
    """A single caption segment with start/end timestamps (in seconds)."""
    start: float
    end: float
    text: str


class CaptionsResponse(BaseModel):
    """Full captions response for a processed video."""
    video_id: str
    source: Optional[str] = None
    language: Optional[str] = None
    captions: List[Caption]


# ── Process Response ──

class ProcessResponse(BaseModel):
    """Response after processing a YouTube URL."""
    video_id: str
    title: str
    duration: float
    video_url: str
    captions: List[Caption]
    source: Optional[str] = None
    language: Optional[str] = None


# ── Export Response ──

class ExportResponse(BaseModel):
    """Response after exporting a trimmed clip."""
    clip_url: str
    captions_url: str
    start: float
    end: float
    duration: float
    caption_count: int
