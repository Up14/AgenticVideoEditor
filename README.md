# Agentic Video Editor

A collection of tools for AI-powered video editing, built toward a fully agentic video pipeline.

## What this is

The goal is to build a set of tools that an AI agent can call to edit videos end to end — picking the best clips, analyzing styles, burning captions, and more. Each tool in this repo is a standalone module that does one specific thing.

**Current state:** The tools work independently as hardcoded flows. Full agentic orchestration (where an AI decides which tools to call and in what order) is the next step.

---

## Tools

### VideoSelection

A web app that downloads a YouTube video, shows an interactive timeline with synced captions, and uses AI to find the best clips for YouTube Shorts.

- Paste a YouTube URL, choose quality, the video downloads automatically
- Interactive timeline with draggable in/out point selection
- AI pipeline (Cerebras LLM + semantic embeddings) scores every segment for viral potential
- One-click export of trimmed clip + captions

[See VideoSelection README](VideoSelection/README.md)

---

### Captions

Upload any video and get back a full JSON breakdown of how its captions are styled. Built for reverse-engineering viral short-form content.

- Detects font, color, stroke, shadow, and position
- Detects entry/exit animations and karaoke-style word highlighting
- Counts cuts per second and zoom events
- Filters out watermarks and brand overlays

[See Captions README](Captions/README.md)

---

### ExistingCode

Older standalone utilities used before the above tools were built:

- **YtVideoDownloader** — Download YouTube videos via a simple Streamlit UI
- **YtCaptionDownloader** — Download captions from YouTube in SRT, VTT, TXT, or JSON format
- **ClipSelector** — Earlier version of the clip scoring logic

---

## Setup

Each tool has its own setup. See the README inside each folder.

Quick links:
- [VideoSelection setup](VideoSelection/README.md)
- [Captions setup](Captions/README.md)

---

## Requirements (shared)

- Python 3.9+
- ffmpeg installed and in PATH
- Node.js 18+ (for VideoSelection frontend only)

---

## Roadmap

- [ ] Wrap each tool as a callable function with a standard interface
- [ ] Build an AI agent layer that chains the tools together
- [ ] Add a B-roll search tool
- [ ] Add an auto-caption burner tool
- [ ] Full end-to-end pipeline: YouTube URL in, finished short-form video out
