import { useRef, useState, useCallback, useEffect } from "react";
import type { Caption } from "../api/client";

interface Props {
  duration: number;
  currentTime: number;
  captions: Caption[];
  selectionStart: number;
  selectionEnd: number;
  onSelectionChange: (start: number, end: number) => void;
  onSeek: (time: number) => void;
}

type DragTarget = "start" | "end" | "region" | null;

/**
 * Interactive SVG timeline with:
 * - Caption segments as labeled blocks
 * - Green selection region with draggable handles
 * - Playhead showing current position
 */
export default function Timeline({
  duration,
  currentTime,
  captions,
  selectionStart,
  selectionEnd,
  onSelectionChange,
  onSeek,
}: Props) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [dragTarget, setDragTarget] = useState<DragTarget>(null);
  const [dragOffset, setDragOffset] = useState(0);

  const PADDING = 12;
  const TIMELINE_HEIGHT = 100;
  const HANDLE_WIDTH = 8;

  // Convert pixel X to time
  const xToTime = useCallback(
    (x: number): number => {
      const svg = svgRef.current;
      if (!svg || duration <= 0) return 0;
      const rect = svg.getBoundingClientRect();
      const usableWidth = rect.width - PADDING * 2;
      const ratio = Math.max(0, Math.min(1, (x - rect.left - PADDING) / usableWidth));
      return ratio * duration;
    },
    [duration]
  );


  // ── Mouse Handlers ──

  const handleMouseDown = useCallback(
    (e: React.MouseEvent, target: DragTarget) => {
      e.preventDefault();
      e.stopPropagation();
      setDragTarget(target);

      if (target === "region") {
        const time = xToTime(e.clientX);
        setDragOffset(time - selectionStart);
      }
    },
    [xToTime, selectionStart]
  );

  const handleTimelineClick = useCallback(
    (e: React.MouseEvent) => {
      if (dragTarget) return;
      const time = xToTime(e.clientX);
      onSeek(time);
    },
    [xToTime, onSeek, dragTarget]
  );

  useEffect(() => {
    if (!dragTarget) return;

    const handleMouseMove = (e: MouseEvent) => {
      const time = xToTime(e.clientX);

      if (dragTarget === "start") {
        const newStart = Math.max(0, Math.min(time, selectionEnd - 1));
        onSelectionChange(newStart, selectionEnd);
      } else if (dragTarget === "end") {
        const newEnd = Math.min(duration, Math.max(time, selectionStart + 1));
        onSelectionChange(selectionStart, newEnd);
      } else if (dragTarget === "region") {
        const selDuration = selectionEnd - selectionStart;
        let newStart = time - dragOffset;
        newStart = Math.max(0, Math.min(newStart, duration - selDuration));
        onSelectionChange(newStart, newStart + selDuration);
      }
    };

    const handleMouseUp = () => setDragTarget(null);

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [
    dragTarget,
    dragOffset,
    selectionStart,
    selectionEnd,
    duration,
    xToTime,
    onSelectionChange,
  ]);

  if (duration <= 0) return null;

  // ── Rendering ──

  // Compute SVG width from container
  const svgWidth = svgRef.current?.getBoundingClientRect().width ?? 800;
  const usableWidth = svgWidth - PADDING * 2;

  const selStartX = PADDING + (selectionStart / duration) * usableWidth;
  const selEndX = PADDING + (selectionEnd / duration) * usableWidth;
  const playheadX = PADDING + (currentTime / duration) * usableWidth;

  return (
    <div className="timeline">
      <svg
        ref={svgRef}
        width="100%"
        height={TIMELINE_HEIGHT}
        onClick={handleTimelineClick}
        style={{ cursor: dragTarget ? "grabbing" : "default" }}
      >
        {/* Background track */}
        <rect
          x={PADDING}
          y={20}
          width={usableWidth}
          height={50}
          rx={4}
          fill="#1e1e2e"
          stroke="#3a3a4e"
          strokeWidth={1}
        />

        {/* Caption segments */}
        {captions.map((cap, i) => {
          const x = PADDING + (cap.start / duration) * usableWidth;
          const w = Math.max(1, ((cap.end - cap.start) / duration) * usableWidth);
          return (
            <rect
              key={i}
              x={x}
              y={22}
              width={w}
              height={46}
              fill="#2a2a42"
              stroke="#4a4a6a"
              strokeWidth={0.5}
              rx={2}
            />
          );
        })}

        {/* Green selection region */}
        <rect
          x={selStartX}
          y={18}
          width={Math.max(0, selEndX - selStartX)}
          height={54}
          fill="rgba(0, 220, 100, 0.2)"
          stroke="rgba(0, 220, 100, 0.6)"
          strokeWidth={1.5}
          rx={3}
          style={{ cursor: "grab" }}
          onMouseDown={(e) => handleMouseDown(e, "region")}
        />

        {/* Left handle */}
        <rect
          x={selStartX - HANDLE_WIDTH / 2}
          y={16}
          width={HANDLE_WIDTH}
          height={58}
          rx={3}
          fill="#00dc64"
          style={{ cursor: "ew-resize" }}
          onMouseDown={(e) => handleMouseDown(e, "start")}
        />

        {/* Right handle */}
        <rect
          x={selEndX - HANDLE_WIDTH / 2}
          y={16}
          width={HANDLE_WIDTH}
          height={58}
          rx={3}
          fill="#00dc64"
          style={{ cursor: "ew-resize" }}
          onMouseDown={(e) => handleMouseDown(e, "end")}
        />

        {/* Playhead */}
        <line
          x1={playheadX}
          y1={12}
          x2={playheadX}
          y2={78}
          stroke="#ff4444"
          strokeWidth={2}
        />
        <polygon
          points={`${playheadX - 5},12 ${playheadX + 5},12 ${playheadX},18`}
          fill="#ff4444"
        />

        {/* Time labels */}
        <text x={PADDING} y={92} fill="#888" fontSize={10}>
          0:00
        </text>
        <text x={PADDING + usableWidth} y={92} fill="#888" fontSize={10} textAnchor="end">
          {Math.floor(duration / 60)}:{Math.floor(duration % 60).toString().padStart(2, "0")}
        </text>
        <text x={selStartX} y={92} fill="#00dc64" fontSize={10} textAnchor="middle">
          {Math.floor(selectionStart / 60)}:
          {Math.floor(selectionStart % 60).toString().padStart(2, "0")}
        </text>
        <text x={selEndX} y={92} fill="#00dc64" fontSize={10} textAnchor="middle">
          {Math.floor(selectionEnd / 60)}:
          {Math.floor(selectionEnd % 60).toString().padStart(2, "0")}
        </text>
      </svg>
    </div>
  );
}
