"""
Pydantic schemas for the ClipSelector API endpoints.
"""

from pydantic import BaseModel
from typing import List


class RankedClip(BaseModel):
    """A single AI-ranked viral clip candidate."""
    title: str
    hook_reason: str
    start: float
    end: float
    duration: float
    start_timestamp: str   # "MM:SS"
    end_timestamp: str     # "MM:SS"
    text: str
    final_score: float
    ai_viral_score: float
    standalone_understanding: float
    resolution_score: float
    context_dependency: float
    local_score: float


class ClipSelectorResponse(BaseModel):
    """Response for POST /api/clip-selector/analyze/{video_id}"""
    video_id: str
    total_clips: int
    clips: List[RankedClip]
