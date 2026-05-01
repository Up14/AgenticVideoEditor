import type { Segment } from "../types";
import { getSegmentColor, formatTime } from "../types";

interface Props {
  segments: Segment[];
  activeSegmentId: string | null;
  duration: number;
  onSegmentChange: (id: string, start: number, end: number) => void;
  onAddSegment: () => void;
  onRemoveSegment: (id: string) => void;
  onSelectSegment: (id: string) => void;
  onExport: () => void;
  onSeekToSegment: (id: string) => void;
  isExporting: boolean;
}

/**
 * Toolbar for managing multiple segments: add/remove, select active,
 * nudge in/out points, and export all segments.
 */
export default function Toolbar({
  segments,
  activeSegmentId,
  duration,
  onSegmentChange,
  onAddSegment,
  onRemoveSegment,
  onSelectSegment,
  onExport,
  onSeekToSegment,
  isExporting,
}: Props) {
  const activeSeg = segments.find((s) => s.id === activeSegmentId);
  const activeIdx = segments.findIndex((s) => s.id === activeSegmentId);
  const palette = activeIdx >= 0 ? getSegmentColor(activeIdx) : null;

  const nudge = (target: "start" | "end", delta: number) => {
    if (!activeSeg) return;
    if (target === "start") {
      const newStart = Math.max(0, Math.min(activeSeg.start + delta, activeSeg.end - 1));
      onSegmentChange(activeSeg.id, newStart, activeSeg.end);
    } else {
      const newEnd = Math.min(duration, Math.max(activeSeg.end + delta, activeSeg.start + 1));
      onSegmentChange(activeSeg.id, activeSeg.start, newEnd);
    }
  };

  const totalDuration = segments.reduce((sum, s) => sum + (s.end - s.start), 0);

  return (
    <div className="toolbar toolbar--multi">
      {/* Segment chips at the top */}
      <div className="toolbar__segments-row">
        <span className="toolbar__label">Segments</span>
        <div className="toolbar__chips">
          {segments.map((seg, i) => {
            const p = getSegmentColor(i);
            const isActive = seg.id === activeSegmentId;
            return (
              <button
                key={seg.id}
                className={`segment-chip ${isActive ? "segment-chip--active" : ""}`}
                style={{
                  borderColor: p.color,
                  background: isActive ? p.dim : "transparent",
                  color: p.color,
                }}
                onClick={() => onSelectSegment(seg.id)}
                title={`Select ${seg.label}`}
              >
                <span className="segment-chip__dot" style={{ background: p.color }} />
                {seg.label}
                <span className="segment-chip__range">
                  {formatTime(seg.start)}-{formatTime(seg.end)}
                </span>
                {segments.length > 1 && (
                  <span
                    className="segment-chip__remove"
                    onClick={(e) => {
                      e.stopPropagation();
                      onRemoveSegment(seg.id);
                    }}
                    title={`Remove ${seg.label}`}
                  >
                    ✕
                  </span>
                )}
              </button>
            );
          })}
          <button
            className="segment-chip segment-chip--add"
            onClick={onAddSegment}
            title="Add new segment"
          >
            + Add
          </button>
        </div>
      </div>

      {/* Active segment controls */}
      {activeSeg && palette && (
        <div className="toolbar__controls-row">
          <div className="toolbar__group">
            <span className="toolbar__label">In Point</span>
            <button onClick={() => nudge("start", -1)} title="Move in -1s">◀</button>
            <span className="toolbar__time" style={{ color: palette.color, background: `${palette.color}20` }}>
              {formatTime(activeSeg.start)}
            </span>
            <button onClick={() => nudge("start", 1)} title="Move in +1s">▶</button>
          </div>

          <div className="toolbar__group">
            <span className="toolbar__label">Out Point</span>
            <button onClick={() => nudge("end", -1)} title="Move out -1s">◀</button>
            <span className="toolbar__time" style={{ color: palette.color, background: `${palette.color}20` }}>
              {formatTime(activeSeg.end)}
            </span>
            <button onClick={() => nudge("end", 1)} title="Move out +1s">▶</button>
          </div>

          <div className="toolbar__group">
            <span className="toolbar__label">Clip</span>
            <span className="toolbar__duration">
              {formatTime(activeSeg.end - activeSeg.start)}
            </span>
          </div>

          <div className="toolbar__group">
            <span className="toolbar__label">Total</span>
            <span className="toolbar__duration">
              {formatTime(totalDuration)}
            </span>
          </div>

          <div className="toolbar__actions">
            <button
              className="btn-secondary"
              onClick={() => onSeekToSegment(activeSeg.id)}
            >
              ⏭ Jump
            </button>
            <button
              className="btn-primary"
              onClick={onExport}
              disabled={isExporting || segments.length === 0}
            >
              {isExporting ? "⏳ Exporting..." : `✂️ Export ${segments.length > 1 ? `All (${segments.length})` : "Clip"}`}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
