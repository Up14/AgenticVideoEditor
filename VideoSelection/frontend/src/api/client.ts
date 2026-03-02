/**
 * API client — communicates with the FastAPI backend.
 */

const API_BASE = "http://localhost:8000";

export interface Caption {
  start: number;
  end: number;
  text: string;
}

export interface ProcessResponse {
  video_id: string;
  title: string;
  duration: number;
  video_url: string;
  captions: Caption[];
  source: string | null;
  language: string | null;
}

export interface ExportResponse {
  clip_url: string;
  captions_url: string;
  start: number;
  end: number;
  duration: number;
  caption_count: number;
}

/**
 * POST /api/process — Download video + extract captions from YT URL.
 */
export async function processVideo(
  url: string,
  quality: number = 720
): Promise<ProcessResponse> {
  const res = await fetch(`${API_BASE}/api/process`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url, quality }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * POST /api/export — Trim video + slice captions.
 */
export async function exportClip(
  videoId: string,
  start: number,
  end: number
): Promise<ExportResponse> {
  const res = await fetch(`${API_BASE}/api/export`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, start, end }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * Returns the full URL for a video stream.
 */
export function getVideoStreamUrl(videoId: string): string {
  return `${API_BASE}/api/video/${videoId}`;
}

/**
 * Returns the full download URL for a clip or captions file.
 */
export function getDownloadUrl(relativePath: string): string {
  return `${API_BASE}${relativePath}`;
}
