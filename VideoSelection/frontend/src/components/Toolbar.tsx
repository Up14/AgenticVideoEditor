interface Props {
  selectionStart: number;
  selectionEnd: number;
  duration: number;
  onSelectionChange: (start: number, end: number) => void;
  onExport: () => void;
  onSeekToSelection: () => void;
  isExporting: boolean;
}

/**
 * Formats seconds to MM:SS display.
 */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return `${m}:${s.toString().padStart(2, "0")}`;
}

/**
 * Toolbar for controlling the green selection region.
 * Provides nudge buttons, in/out point display, and export.
 */
export default function Toolbar({
  selectionStart,
  selectionEnd,
  duration,
  onSelectionChange,
  onExport,
  onSeekToSelection,
  isExporting,
}: Props) {
  const nudge = (target: "start" | "end", delta: number) => {
    if (target === "start") {
      const newStart = Math.max(0, Math.min(selectionStart + delta, selectionEnd - 1));
      onSelectionChange(newStart, selectionEnd);
    } else {
      const newEnd = Math.min(duration, Math.max(selectionEnd + delta, selectionStart + 1));
      onSelectionChange(selectionStart, newEnd);
    }
  };

  const clipDuration = selectionEnd - selectionStart;

  return (
    <div className="toolbar">
      <div className="toolbar__group">
        <span className="toolbar__label">In Point</span>
        <button onClick={() => nudge("start", -1)} title="Move in point 1s earlier">
          ◀
        </button>
        <span className="toolbar__time">{formatTime(selectionStart)}</span>
        <button onClick={() => nudge("start", 1)} title="Move in point 1s later">
          ▶
        </button>
      </div>

      <div className="toolbar__group">
        <span className="toolbar__label">Out Point</span>
        <button onClick={() => nudge("end", -1)} title="Move out point 1s earlier">
          ◀
        </button>
        <span className="toolbar__time">{formatTime(selectionEnd)}</span>
        <button onClick={() => nudge("end", 1)} title="Move out point 1s later">
          ▶
        </button>
      </div>

      <div className="toolbar__group">
        <span className="toolbar__label">Duration</span>
        <span className="toolbar__duration">{formatTime(clipDuration)}</span>
      </div>

      <div className="toolbar__actions">
        <button className="btn-secondary" onClick={onSeekToSelection}>
          ⏭ Jump to Selection
        </button>
        <button
          className="btn-primary"
          onClick={onExport}
          disabled={isExporting || clipDuration < 1}
        >
          {isExporting ? "⏳ Exporting..." : "✂️ Export Clip"}
        </button>
      </div>
    </div>
  );
}
