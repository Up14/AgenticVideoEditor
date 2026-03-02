import { useRef, useState, useCallback, useEffect } from "react";
import type { Caption } from "../api/client";
import type { Segment } from "../types";
import { getSegmentColor } from "../types";

interface Props {
  duration: number;
  currentTime: number;
  captions: Caption[];
  segments: Segment[];
  activeSegmentId: string | null;
  onSegmentChange: (id: string, start: number, end: number) => void;
  onSegmentSelect: (id: string) => void;
  onSeek: (time: number) => void;
}

type DragTarget = { segmentId: string; handle: "start" | "end" | "region" } | null;

/**
 * Interactive SVG timeline supporting multiple colored segments.
 */
export default function Timeline({
  duration,
  currentTime,
  captions,
  segments,
  activeSegmentId,
  onSegmentChange,
  onSegmentSelect,
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
    (e: React.MouseEvent, segmentId: string, handle: "start" | "end" | "region") => {
      e.preventDefault();
      e.stopPropagation();
      setDragTarget({ segmentId, handle });
      onSegmentSelect(segmentId);

      if (handle === "region") {
        const seg = segments.find((s) => s.id === segmentId);
        if (seg) {
          const time = xToTime(e.clientX);
          setDragOffset(time - seg.start);
        }
      }
    },
    [xToTime, segments, onSegmentSelect]
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

    const seg = segments.find((s) => s.id === dragTarget.segmentId);
    if (!seg) return;

    const handleMouseMove = (e: MouseEvent) => {
      const time = xToTime(e.clientX);

      if (dragTarget.handle === "start") {
        const newStart = Math.max(0, Math.min(time, seg.end - 1));
        onSegmentChange(dragTarget.segmentId, newStart, seg.end);
      } else if (dragTarget.handle === "end") {
        const newEnd = Math.min(duration, Math.max(time, seg.start + 1));
        onSegmentChange(dragTarget.segmentId, seg.start, newEnd);
      } else if (dragTarget.handle === "region") {
        const segDuration = seg.end - seg.start;
        let newStart = time - dragOffset;
        newStart = Math.max(0, Math.min(newStart, duration - segDuration));
        onSegmentChange(dragTarget.segmentId, newStart, newStart + segDuration);
      }
    };

    const handleMouseUp = () => setDragTarget(null);

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [dragTarget, dragOffset, segments, duration, xToTime, onSegmentChange]);

  if (duration <= 0) return null;

  // ── Rendering ──

  const svgWidth = svgRef.current?.getBoundingClientRect().width ?? 800;
  const usableWidth = svgWidth - PADDING * 2;
  const playheadX = PADDING + (currentTime / duration) * usableWidth;

  // find the color index for each segment (stable by original order)
  const segmentColorIndex = new Map<string, number>();
  segments.forEach((seg, i) => segmentColorIndex.set(seg.id, i));

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

        {/* Selection segments */}
        {segments.map((seg) => {
          const idx = segmentColorIndex.get(seg.id) ?? 0;
          const palette = getSegmentColor(idx);
          const isActive = seg.id === activeSegmentId;
          const startX = PADDING + (seg.start / duration) * usableWidth;
          const endX = PADDING + (seg.end / duration) * usableWidth;

          return (
            <g key={seg.id}>
              {/* Region overlay */}
              <rect
                x={startX}
                y={18}
                width={Math.max(0, endX - startX)}
                height={54}
                fill={palette.dim}
                stroke={palette.color}
                strokeWidth={isActive ? 2 : 1}
                strokeDasharray={isActive ? "none" : "4 2"}
                rx={3}
                style={{ cursor: "grab" }}
                onMouseDown={(e) => handleMouseDown(e, seg.id, "region")}
              />

              {/* Left handle */}
              <rect
                x={startX - HANDLE_WIDTH / 2}
                y={16}
                width={HANDLE_WIDTH}
                height={58}
                rx={3}
                fill={palette.color}
                opacity={isActive ? 1 : 0.7}
                style={{ cursor: "ew-resize" }}
                onMouseDown={(e) => handleMouseDown(e, seg.id, "start")}
              />

              {/* Right handle */}
              <rect
                x={endX - HANDLE_WIDTH / 2}
                y={16}
                width={HANDLE_WIDTH}
                height={58}
                rx={3}
                fill={palette.color}
                opacity={isActive ? 1 : 0.7}
                style={{ cursor: "ew-resize" }}
                onMouseDown={(e) => handleMouseDown(e, seg.id, "end")}
              />

              {/* Segment label */}
              {endX - startX > 30 && (
                <text
                  x={startX + (endX - startX) / 2}
                  y={48}
                  fill={palette.color}
                  fontSize={9}
                  fontWeight={600}
                  textAnchor="middle"
                  style={{ pointerEvents: "none" }}
                >
                  {seg.label}
                </text>
              )}
            </g>
          );
        })}

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

        {/* Time labels: endpoints */}
        <text x={PADDING} y={92} fill="#888" fontSize={10}>
          0:00
        </text>
        <text x={PADDING + usableWidth} y={92} fill="#888" fontSize={10} textAnchor="end">
          {Math.floor(duration / 60)}:{Math.floor(duration % 60).toString().padStart(2, "0")}
        </text>

        {/* Active segment time labels */}
        {segments
          .filter((seg) => seg.id === activeSegmentId)
          .map((seg) => {
            const palette = getSegmentColor(segmentColorIndex.get(seg.id) ?? 0);
            const sx = PADDING + (seg.start / duration) * usableWidth;
            const ex = PADDING + (seg.end / duration) * usableWidth;
            return (
              <g key={`labels-${seg.id}`}>
                <text x={sx} y={92} fill={palette.color} fontSize={10} textAnchor="middle">
                  {Math.floor(seg.start / 60)}:
                  {Math.floor(seg.start % 60).toString().padStart(2, "0")}
                </text>
                <text x={ex} y={92} fill={palette.color} fontSize={10} textAnchor="middle">
                  {Math.floor(seg.end / 60)}:
                  {Math.floor(seg.end % 60).toString().padStart(2, "0")}
                </text>
              </g>
            );
          })}
      </svg>
    </div>
  );
}
