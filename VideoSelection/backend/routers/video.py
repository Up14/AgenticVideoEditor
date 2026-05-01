"""
Video router — serves downloaded video files with HTTP Range request support.

Range requests (HTTP 206 Partial Content) are REQUIRED for HTML5 video
seeking to work. Without them, the browser cannot jump to arbitrary
positions in the video — the playhead stays stuck at the beginning.
"""

import os
import logging
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from services.downloader import get_video_path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["video"])

CHUNK_SIZE = 1024 * 1024  # 1 MB chunks for streaming


@router.get("/video/{video_id}")
async def stream_video(video_id: str, request: Request):
    """
    Serves the downloaded video file with Range request support.

    - No Range header → 200 OK (full file)
    - Range header    → 206 Partial Content (byte range)

    This is essential for HTML5 <video> seeking to work.
    """
    path = get_video_path(video_id)
    if not path:
        raise HTTPException(status_code=404, detail="Video not found")

    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=START-END" or "bytes=START-"
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1

        # Clamp to valid range
        start = max(0, start)
        end = min(end, file_size - 1)
        content_length = end - start + 1

        def iter_file():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type="video/mp4",
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Cache-Control": "no-cache",
            },
        )

    # No Range header → serve the full file
    def iter_full():
        with open(path, "rb") as f:
            while chunk := f.read(CHUNK_SIZE):
                yield chunk

    return StreamingResponse(
        iter_full(),
        status_code=200,
        media_type="video/mp4",
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )
