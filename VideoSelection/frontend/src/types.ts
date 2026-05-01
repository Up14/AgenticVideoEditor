/**
 * Shared data types used across the application.
 */

/**
 * A single clip segment on the timeline.
 */
export interface Segment {
  id: string;
  start: number;
  end: number;
  color: string;
  label: string;
}

/**
 * Pre-defined segment color palette — visually distinct on dark background.
 * Each entry has a fill color and a dimmed version for the overlay.
 */
export const SEGMENT_COLORS = [
  { color: "#a855f7", dim: "rgba(168, 85, 247, 0.2)",  name: "Purple" },
  { color: "#3b82f6", dim: "rgba(59, 130, 246, 0.2)",  name: "Blue" },
  { color: "#ef4444", dim: "rgba(239, 68, 68, 0.2)",   name: "Red" },
  { color: "#f59e0b", dim: "rgba(245, 158, 11, 0.2)",  name: "Amber" },
  { color: "#10b981", dim: "rgba(16, 185, 129, 0.2)",  name: "Emerald" },
  { color: "#06b6d4", dim: "rgba(6, 182, 212, 0.2)",   name: "Cyan" },
  { color: "#f97316", dim: "rgba(249, 115, 22, 0.2)",  name: "Orange" },
  { color: "#ec4899", dim: "rgba(236, 72, 153, 0.2)",  name: "Pink" },
];

/**
 * Gets the color entry for a segment index (cycles if more than palette size).
 */
export function getSegmentColor(index: number) {
  return SEGMENT_COLORS[index % SEGMENT_COLORS.length];
}

/**
 * Utility: generate a short unique ID.
 */
export function generateId(): string {
  return Math.random().toString(36).slice(2, 10);
}

/**
 * Merge overlapping segments (sorted by start time).
 * When two segments overlap, they are merged into one,
 * keeping the color/label of the earlier segment.
 */
export function mergeOverlappingSegments(segments: Segment[]): Segment[] {
  if (segments.length <= 1) return segments;

  // Sort by start time
  const sorted = [...segments].sort((a, b) => a.start - b.start);
  const merged: Segment[] = [sorted[0]];

  for (let i = 1; i < sorted.length; i++) {
    const last = merged[merged.length - 1];
    const curr = sorted[i];

    if (curr.start <= last.end) {
      // Overlap detected → merge into the earlier segment
      merged[merged.length - 1] = {
        ...last,
        end: Math.max(last.end, curr.end),
      };
    } else {
      merged.push(curr);
    }
  }

  return merged;
}

/**
 * Format seconds to MM:SS display.
 */
export function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Format seconds to MM:SS.s display (with tenths).
 */
export function formatTimePrecise(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}:${parseFloat(s) < 10 ? "0" : ""}${s}`;
}
