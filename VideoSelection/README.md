# Video Selection Tool

A web-based video clip editor that downloads YouTube videos, displays an interactive timeline with caption synchronization, exports trimmed clips, and uses AI to automatically detect the most viral-worthy segments.

## Architecture

```
VideoSelection/
├── start.sh               # One-command launcher (auto-installs all deps)
├── backend/               # Python FastAPI server
│   ├── main.py            # Entry point (uvicorn)
│   ├── .env               # Environment variables (API keys)
│   ├── requirements.txt
│   ├── routers/           # API endpoints
│   │   ├── process.py     # POST /api/process — download video + extract captions
│   │   ├── video.py       # GET /api/video/{id} — stream video file
│   │   ├── captions.py    # GET /api/captions/{id} — get parsed captions
│   │   ├── export.py      # POST /api/export — trim video + slice captions
│   │   └── cookies.py     # POST /api/cookies/extract, GET /api/cookies/status
│   ├── services/          # Business logic
│   │   ├── downloader.py        # yt-dlp video download wrapper
│   │   ├── caption_service.py   # Caption extraction, parsing, deduplication
│   │   ├── trimmer.py           # ffmpeg trimming + caption slicing
│   │   └── cookie_service.py    # Chrome cookie extraction for yt-dlp auth
│   ├── models/
│   │   └── schemas.py     # Pydantic request/response models
│   └── clip_selector/     # AI viral clip detection pipeline
│       ├── router.py      # POST /api/clip-selector/analyze/{id}, GET /export-csv
│       ├── service.py     # Pipeline orchestrator
│       ├── nlp_service.py        # spaCy transcript parsing + sentence reconstruction
│       ├── semantic_service.py   # Embeddings, emotion intensity, boundary detection
│       ├── candidate_service.py  # Clip candidate generation, scoring, deduplication
│       ├── ai_ranking_service.py # Cerebras LLM viral scoring (batched)
│       ├── config.py      # Pipeline configuration constants
│       └── schemas.py     # Pydantic models for clip selector API
│
├── frontend/              # React + Vite + TypeScript
│   └── src/
│       ├── App.tsx                  # Main orchestrator + cookie gate
│       ├── components/
│       │   ├── URLInput.tsx         # YouTube URL + quality input form
│       │   ├── VideoPlayer.tsx      # HTML5 video wrapper with controls
│       │   ├── Timeline.tsx         # SVG timeline with draggable selection
│       │   ├── CaptionPanel.tsx     # Dual-section caption display
│       │   ├── Toolbar.tsx          # In/Out point controls + export
│       │   ├── CookieConsentModal.tsx  # Cookie access consent UI
│       │   └── CookieConsentModal.css
│       ├── hooks/
│       │   ├── useVideoSync.ts      # Video ↔ timeline sync via requestAnimationFrame
│       │   └── useCaptions.ts       # Caption filtering by time/selection
│       └── api/
│           └── client.ts            # Typed API client (includes extractCookies())
└── README.md
```

## Features

- **YouTube Video Loading** — Paste a URL, choose quality (360p–1080p), downloads video + extracts captions automatically
- **Interactive Timeline** — SVG-based timeline showing caption segments, a red playhead, and a draggable green selection region
- **Caption Synchronization** — Captions scroll and highlight in sync with video playback
- **Clip Selection** — Drag green handles or use `I`/`O` keyboard shortcuts to set in/out points
- **Clip Export** — One-click export produces a trimmed `.mp4` + trimmed captions JSON
- **AI Viral Clip Detection** — Runs a full NLP + semantic + LLM pipeline (Cerebras) to rank the best clips for YouTube Shorts
- **CSV Export** — Export final clip timestamps + captions as a CSV
- **Cookie Consent Gate** — On first load, prompts to extract Chrome cookies so yt-dlp can download age-restricted / private videos
- **Keyboard Shortcuts** — `Space` (play/pause), `I` (set in point), `O` (set out point), `←/→` (seek ±5s)

## Prerequisites

- **Python 3.9+**
- **Node.js 18+** with npm
- **ffmpeg** installed and in PATH

### Install ffmpeg

```bash
# macOS
brew install ffmpeg

# Ubuntu/Debian
sudo apt install ffmpeg
```

## Quick Start (Recommended)

Clone the repo and run the single start script — it automatically creates the Python venv, installs all dependencies, and launches both servers:

```bash
git clone https://github.com/Up14/AgenticVideoEditor.git
cd AgenticVideoEditor/VideoSelection
bash start.sh
```

Open **http://localhost:9636** in your browser.

The script handles everything on first run:
- Creates `backend/venv/` and installs Python packages from `requirements.txt`
- Runs `npm install` for the frontend if `node_modules/` is missing
- Starts backend on port **9637** and frontend on port **9636**

## Manual Setup (Alternative)

### Backend

```bash
cd VideoSelection/backend
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
uvicorn main:app --reload --port 9637
```

### Frontend

```bash
cd VideoSelection/frontend
npm install
npm run dev
```

## Environment Variables

The `.env` file is committed at `VideoSelection/backend/.env`:

| Variable | Description |
|---|---|
| `CEREBRAS_API_KEYS` | Comma-separated Cerebras API keys for AI viral clip scoring |

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/process` | POST | Download video + extract captions from YouTube URL |
| `/api/video/{id}` | GET | Stream the downloaded video file |
| `/api/captions/{id}` | GET | Get parsed captions with timestamps |
| `/api/export` | POST | Trim video to selection + slice captions |
| `/api/download/clip/{id}/{file}` | GET | Download the trimmed clip |
| `/api/download/captions/{id}/{file}` | GET | Download the trimmed captions |
| `/api/clip-selector/analyze/{id}` | POST | Run AI pipeline — returns ranked viral clip candidates |
| `/api/clip-selector/export-csv/{id}` | GET | Export clip timestamps + captions as CSV |
| `/api/cookies/extract` | POST | Extract Chrome cookies for yt-dlp authentication |
| `/api/cookies/status` | GET | Check if cookies file is available |

## AI Clip Selector Pipeline

The clip selector runs automatically after a video is processed:

1. **NLP** — spaCy tokenises the transcript and reconstructs clean sentences
2. **Semantic analysis** — sentence-transformers embeddings + emotion intensity scoring
3. **Candidate generation** — sliding window + boundary detection produces clip candidates
4. **Local scoring** — heuristic scores (standalone understanding, resolution, context dependency)
5. **AI ranking** — Cerebras LLM scores each candidate for viral potential in batches of 6
6. **Deduplication** — semantic deduplication removes overlapping clips
7. **Final ranking** — combined score sorts clips for display

## Tech Stack

| Layer | Technology |
|---|---|
| Frontend | React + Vite + TypeScript |
| Styling | Vanilla CSS (dark theme) |
| Backend | Python FastAPI + uvicorn |
| Video Download | yt-dlp |
| Video Trimming | ffmpeg |
| Data Validation | Pydantic v2 |
| NLP | spaCy |
| Embeddings | sentence-transformers |
| AI Scoring | Cerebras Cloud SDK (LLM) |
