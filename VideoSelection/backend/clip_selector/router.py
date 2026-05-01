"""
Clip Selector Router — FastAPI endpoints for AI-powered viral clip detection.
Part of the clip_selector package.

POST /api/clip-selector/analyze/{video_id}   — runs full pipeline, returns ranked clips
GET  /api/clip-selector/export-csv/{video_id} — returns CSV with final user timestamps
"""

import csv
import io
import json
import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from clip_selector.schemas import ClipSelectorResponse, RankedClip
from clip_selector.service import run_clip_selector
from services.caption_service import get_captions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/clip-selector", tags=["clip-selector"])


@router.post("/analyze/{video_id}", response_model=ClipSelectorResponse)
async def analyze_clips(video_id: str):
    """
    Runs the full ClipSelector pipeline on a previously processed video.

    Prerequisites:
      POST /api/process must have been called first (saves captions.json to disk).

    Returns:
      Ranked list of viral clip candidates with scores, timestamps, titles, and hooks.
    """
    logger.info(">>> BEGIN Clip selector analysis for video_id=%s", video_id)
    import time
    start_time = time.perf_counter()
    
    try:
        ranked_clips = run_clip_selector(video_id)
    except ValueError as e:
        logger.warning("[%s] Validation error: %s", video_id, e)
        raise HTTPException(status_code=404, detail=f"Validation error: {e}")
    except RuntimeError as e:
        logger.error("[%s] Pipeline runtime error: %s", video_id, e)
        raise HTTPException(status_code=500, detail=f"Pipeline error: {e}")
    except Exception as e:
        logger.exception("[%s] Unexpected critical failure", video_id)
        raise HTTPException(status_code=500, detail=f"Unexpected failure in clip selection: {type(e).__name__}: {e}")

    duration = time.perf_counter() - start_time
    logger.info("<<< END Clip selector analysis for video_id=%s (Total: %.2fs, Clips: %d)", 
                video_id, duration, len(ranked_clips))
    
    clips = [RankedClip(**c) for c in ranked_clips]
    return ClipSelectorResponse(
        video_id=video_id,
        total_clips=len(clips),
        clips=clips,
    )


@router.get("/export-csv/{video_id}")
async def export_clips_csv(
    video_id: str,
    segments: str = Query(
        ...,
        description=(
            "JSON-encoded array of segments with user-edited timestamps. "
            "Format: [{\"label\": \"Clip 1\", \"start\": 134.5, \"end\": 192.0}, ...]"
        )
    ),
):
    """
    Returns a CSV file with clip timestamps + captions text.

    'segments' must contain the user's FINAL (possibly edited) clip boundaries.

    CSV columns: clip_label, start_timestamp, end_timestamp, start_seconds, end_seconds, caption_text
    """
    try:
        segs = json.loads(segments)
        if not isinstance(segs, list):
            raise ValueError("segments must be a JSON array")
    except (json.JSONDecodeError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Invalid segments parameter: {e}")

    caption_data = get_captions(video_id)
    if not caption_data:
        raise HTTPException(
            status_code=404,
            detail=f"No captions found for video_id='{video_id}'. Run /api/process first."
        )
    all_captions = caption_data.get("captions", [])

    def _fmt(seconds: float) -> str:
        s = max(0, int(seconds))
        return f"{s // 60}:{s % 60:02d}"

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "clip_label", "start_timestamp", "end_timestamp",
        "start_seconds", "end_seconds", "caption_text",
    ])

    for seg in segs:
        label = seg.get("label", "Clip")
        start = float(seg.get("start", 0))
        end   = float(seg.get("end", 0))

        clip_captions = [
            c for c in all_captions
            if c["end"] > start and c["start"] < end
        ]
        caption_text = " ".join(c["text"] for c in clip_captions).strip()

        writer.writerow([label, _fmt(start), _fmt(end), round(start, 3), round(end, 3), caption_text])

    csv_bytes = output.getvalue().encode("utf-8")

    return StreamingResponse(
        io.BytesIO(csv_bytes),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="clips_{video_id}.csv"'},
    )
