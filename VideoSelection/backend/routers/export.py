"""
Export router — trims video and slices captions for selected regions.
Supports both single-segment and multi-segment exports.
"""

import os
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from models.schemas import (
    ExportRequest,
    ExportResponse,
    MultiExportRequest,
    MultiExportResponse,
    SegmentExportResult,
)
from services.trimmer import trim_video, slice_captions, save_trimmed_captions
from services.caption_service import get_captions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["export"])

MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")


@router.post("/export", response_model=ExportResponse)
async def export_clip(req: ExportRequest):
    """
    Trims the video to the selected region and produces
    a trimmed captions file (single segment).
    """
    if req.start >= req.end:
        raise HTTPException(status_code=400, detail="Start must be before end")

    try:
        clip_path = trim_video(req.video_id, req.start, req.end)

        caption_data = get_captions(req.video_id)
        if caption_data and caption_data.get("captions"):
            trimmed_caps = slice_captions(caption_data["captions"], req.start, req.end)
        else:
            trimmed_caps = []

        captions_path = save_trimmed_captions(
            req.video_id, trimmed_caps, req.start, req.end
        )

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


@router.post("/export/multi", response_model=MultiExportResponse)
async def export_multiple_clips(req: MultiExportRequest):
    """
    Exports multiple segments as separate video clips and caption files.
    Each segment produces its own clip + captions pair.
    """
    if not req.segments:
        raise HTTPException(status_code=400, detail="No segments provided")

    results: list[SegmentExportResult] = []

    # Load captions once
    caption_data = get_captions(req.video_id)
    all_captions = caption_data.get("captions", []) if caption_data else []

    for i, seg in enumerate(req.segments):
        if seg.start >= seg.end:
            raise HTTPException(
                status_code=400,
                detail=f"Segment '{seg.label}': start must be before end",
            )

        try:
            # Use segment index as suffix for unique filenames
            clip_path = trim_video(
                req.video_id, seg.start, seg.end, suffix=f"_seg{i+1}"
            )

            trimmed_caps = slice_captions(all_captions, seg.start, seg.end)
            captions_path = save_trimmed_captions(
                req.video_id, trimmed_caps, seg.start, seg.end, suffix=f"_seg{i+1}"
            )

            clip_url = f"/api/download/clip/{req.video_id}/{os.path.basename(clip_path)}"
            captions_url = f"/api/download/captions/{req.video_id}/{os.path.basename(captions_path)}"

            results.append(
                SegmentExportResult(
                    label=seg.label,
                    clip_url=clip_url,
                    captions_url=captions_url,
                    start=seg.start,
                    end=seg.end,
                    duration=round(seg.end - seg.start, 3),
                    caption_count=len(trimmed_caps),
                )
            )

            logger.info(
                "Exported segment %d (%s): %.1f-%.1fs (%d captions)",
                i + 1, seg.label, seg.start, seg.end, len(trimmed_caps),
            )

        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            logger.exception("Export failed for segment %d of %s", i + 1, req.video_id)
            raise HTTPException(status_code=500, detail=f"Segment '{seg.label}': {e}")

    return MultiExportResponse(
        segments=results,
        total_segments=len(results),
    )


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
