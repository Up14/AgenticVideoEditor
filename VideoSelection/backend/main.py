"""
FastAPI entry point for the Video Selection Tool backend.

Serves:
- /api/process     — Download video + extract captions from YouTube URL
- /api/video/{id}  — Stream downloaded video
- /api/captions/{id} — Get parsed captions
- /api/export      — Trim video + slice captions
- /api/download/*  — Serve trimmed clips and captions
- /api/clip-selector/* — AI viral clip detection (see clip_selector/ package)
"""

import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import process, video, captions, export
from clip_selector.router import router as clip_selector_router

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)

# ── App ──
app = FastAPI(
    title="Video Selection Tool API",
    description="Backend API for the Video Selection Tool — "
                "downloads YouTube videos, extracts captions, and exports trimmed clips.",
    version="1.0.0",
)

# ── CORS — allow the Vite dev server ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──
app.include_router(process.router)
app.include_router(video.router)
app.include_router(captions.router)
app.include_router(export.router)
app.include_router(clip_selector_router)


@app.get("/")
async def root():
    return {"status": "ok", "service": "Video Selection Tool API"}
