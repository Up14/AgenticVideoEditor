# Video Selection Tool

A web-based video clip editor that downloads YouTube videos, displays an interactive timeline with caption synchronization, and exports trimmed clips with their corresponding captions.

## Architecture

```
VideoSelection/
├── backend/           # Python FastAPI server
│   ├── main.py        # Entry point (uvicorn)
│   ├── routers/       # API endpoints
│   │   ├── process.py   # POST /api/process — download video + extract captions
│   │   ├── video.py     # GET /api/video/{id} — stream video file
│   │   ├── captions.py  # GET /api/captions/{id} — get parsed captions
│   │   └── export.py    # POST /api/export — trim video + slice captions
│   ├── services/      # Business logic
│   │   ├── downloader.py       # yt-dlp video download wrapper
│   │   ├── caption_service.py  # Caption extraction, parsing, deduplication
│   │   └── trimmer.py          # ffmpeg trimming + caption slicing
│   └── models/
│       └── schemas.py  # Pydantic request/response models
│
├── frontend/          # React + Vite + TypeScript
│   └── src/
│       ├── App.tsx              # Main orchestrator
│       ├── components/
│       │   ├── URLInput.tsx     # YouTube URL + quality input form
│       │   ├── VideoPlayer.tsx  # HTML5 video wrapper with controls
│       │   ├── Timeline.tsx     # SVG timeline with draggable selection
│       │   ├── CaptionPanel.tsx # Dual-section caption display
│       │   └── Toolbar.tsx      # In/Out point controls + export
│       ├── hooks/
│       │   ├── useVideoSync.ts  # Video ↔ timeline sync via requestAnimationFrame
│       │   └── useCaptions.ts   # Caption filtering by time/selection
│       └── api/
│           └── client.ts        # Typed API client
└── README.md
```

## Features

- **YouTube Video Loading** — Paste a URL, choose quality (360p–1080p), and the tool downloads the video + extracts captions automatically
- **Interactive Timeline** — SVG-based timeline showing caption segments, a red playhead, and a green draggable selection region
- **Caption Synchronization** — Captions scroll and highlight in sync with video playback
- **Clip Selection** — Drag green handles or use `I`/`O` keyboard shortcuts to set in/out points
- **Clip Export** — One-click export produces a trimmed `.mp4` file + trimmed captions JSON
- **Keyboard Shortcuts** — `Space` (play/pause), `I` (set in point), `O` (set out point), `←/→` (seek ±5s)

## Prerequisites

- **Python 3.9+** with pip
- **Node.js 18+** with npm
- **ffmpeg** installed and in PATH
- **yt-dlp** (installed via requirements.txt)

### Install ffmpeg (macOS)

```bash
brew install ffmpeg
```

## How to Run

### 1. Start the Backend

```bash
cd VideoSelection/backend

# Create virtual environment (first time only)
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Start the FastAPI server
uvicorn main:app --reload --port 8000
```

The backend API will be available at `http://localhost:8000`.

### 2. Start the Frontend

```bash
cd VideoSelection/frontend

# Install dependencies (first time only)
npm install

# Start the Vite dev server
npm run dev
```

The frontend will be available at `http://localhost:5173`.

### 3. Use the Tool

1. Open `http://localhost:5173` in your browser
2. Paste a YouTube URL and select video quality
3. Click **Load Video** — the tool downloads the video and extracts captions
4. Use the **timeline** to select a clip region (drag green handles or use `I`/`O` keys)
5. Click **Export Clip** to trim the video and download the result

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/process` | POST | Download video + extract captions from YouTube URL |
| `/api/video/{id}` | GET | Stream the downloaded video file |
| `/api/captions/{id}` | GET | Get parsed captions with timestamps |
| `/api/export` | POST | Trim video to selection + slice captions |
| `/api/download/clip/{id}/{file}` | GET | Download the trimmed clip |
| `/api/download/captions/{id}/{file}` | GET | Download the trimmed captions |

## Tech Stack

| Layer | Technology | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Component-based UI with real-time state sync |
| Styling | Vanilla CSS (dark theme) | Full control, no framework overhead |
| Backend | Python FastAPI | Async, reuses existing yt-dlp/caption code |
| Video Download | yt-dlp | Best-in-class YouTube downloader |
| Video Trimming | ffmpeg | Industry-standard frame-accurate cutting |
| Data Validation | Pydantic v2 | Type-safe API contracts |
