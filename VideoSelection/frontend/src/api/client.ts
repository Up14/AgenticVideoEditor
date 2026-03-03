/**
 * API client — communicates with the FastAPI backend.
 */

const API_BASE = "http://127.0.0.1:8000";

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

export interface SegmentExportResult {
  label: string;
  clip_url: string;
  captions_url: string;
  start: number;
  end: number;
  duration: number;
  caption_count: number;
}

export interface MultiExportResponse {
  segments: SegmentExportResult[];
  total_segments: number;
}

export interface RankedClip {
  title: string;
  hook_reason: string;
  start: number;
  end: number;
  duration: number;
  start_timestamp: string;
  end_timestamp: string;
  text: string;
  final_score: number;
  ai_viral_score: number;
  standalone_understanding: number;
  resolution_score: number;
  context_dependency: number;
  local_score: number;
}

export interface ClipSelectorResponse {
  video_id: string;
  total_clips: number;
  clips: RankedClip[];
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
 * POST /api/export/multi — Export multiple segments as separate files.
 */
export async function exportMultipleClips(
  videoId: string,
  segments: { label: string; start: number; end: number }[]
): Promise<MultiExportResponse> {
  const res = await fetch(`${API_BASE}/api/export/multi`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_id: videoId, segments }),
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

/**
 * POST /api/clip-selector/analyze/{videoId}
 * Runs the full AI clip selection pipeline and returns ranked clips.
 */
export async function analyzeClips(videoId: string): Promise<ClipSelectorResponse> {
  const res = await fetch(`${API_BASE}/api/clip-selector/analyze/${videoId}`, {
    method: "POST",
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.json();
}

/**
 * GET /api/clip-selector/export-csv/{videoId}
 * Returns a CSV Blob with clip timestamps + caption text.
 * 'segments' are the user's FINAL (possibly edited) clip boundaries.
 */
export async function exportClipsCSV(
  videoId: string,
  segments: { label: string; start: number; end: number }[]
): Promise<Blob> {
  const encoded = encodeURIComponent(JSON.stringify(segments));
  const res = await fetch(
    `${API_BASE}/api/clip-selector/export-csv/${videoId}?segments=${encoded}`
  );

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: "Unknown error" }));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  return res.blob();
}
