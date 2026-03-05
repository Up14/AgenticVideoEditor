import { useRef, useEffect, useCallback, useState } from "react";
import type { Caption } from "../api/client";
import type { Segment } from "../types";
import { getSegmentColor, formatTimePrecise, formatTime } from "../types";

interface Props {
  captions: Caption[];
  segments: Segment[];
  activeSegmentId: string | null;
  duration: number;
  activeCaption: Caption | null;
  activeCaptionIndex: number;
  onSeek: (time: number) => void;
  onSegmentChange: (id: string, start: number, end: number) => void;
}

/**
 * Sidebar caption panel with draggable in/out handles overlaid on the caption list.
 * Drag the top handle to set the clip start, bottom handle to set clip end.
 */
export default function CaptionPanel({
  captions,
  segments,
  activeSegmentId,
  duration,
  activeCaption,
  activeCaptionIndex,
  onSeek,
  onSegmentChange,
}: Props) {
  const listRef = useRef<HTMLDivElement>(null);
  const [dragging, setDragging] = useState<"in" | "out" | null>(null);

  const activeSeg = segments.find((s) => s.id === activeSegmentId);
  const activeIdx = segments.findIndex((s) => s.id === activeSegmentId);
  const palette = activeIdx >= 0 ? getSegmentColor(activeIdx) : null;

  // Auto-scroll to active caption
  useEffect(() => {
    if (activeCaptionIndex >= 0 && listRef.current) {
      const activeEl = listRef.current.querySelector(
        `[data-caption-index="${activeCaptionIndex}"]`
      ) as HTMLElement | null;
      if (activeEl) {
        const container = listRef.current;
        const elTop = activeEl.offsetTop - container.offsetTop;
        const elCenter = elTop - container.clientHeight / 2 + activeEl.clientHeight / 2;
        container.scrollTo({ top: elCenter, behavior: "smooth" });
      }
    }
  }, [activeCaptionIndex]);

  const getColorForCaption = (cap: Caption): string | null => {
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      if (cap.end > seg.start && cap.start < seg.end) {
        return getSegmentColor(i).color;
      }
    }
    return null;
  };

  // Find caption index at a given Y offset in the list
  const getCaptionAtY = useCallback(
    (clientY: number): Caption | null => {
      if (!listRef.current) return null;
      const items = listRef.current.querySelectorAll("[data-caption-index]");
      for (const item of items) {
        const rect = item.getBoundingClientRect();
        if (clientY >= rect.top && clientY <= rect.bottom) {
          const idx = parseInt(item.getAttribute("data-caption-index") || "0");
          return captions[idx] || null;
        }
      }
      // If above all items, return first; if below, return last
      if (items.length > 0) {
        const firstRect = items[0].getBoundingClientRect();
        if (clientY < firstRect.top) return captions[0];
        const lastRect = items[items.length - 1].getBoundingClientRect();
        if (clientY > lastRect.bottom) return captions[captions.length - 1];
      }
      return null;
    },
    [captions]
  );

  // Handle drag
  useEffect(() => {
    if (!dragging || !activeSeg) return;

    const handleMouseMove = (e: MouseEvent) => {
      const cap = getCaptionAtY(e.clientY);
      if (!cap) return;

      if (dragging === "in") {
        const newStart = Math.min(cap.start, activeSeg.end - 1);
        onSegmentChange(activeSeg.id, newStart, activeSeg.end);
      } else {
        const newEnd = Math.max(cap.end, activeSeg.start + 1);
        onSegmentChange(activeSeg.id, activeSeg.start, newEnd);
      }
    };

    const handleMouseUp = () => setDragging(null);

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);
    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
    };
  }, [dragging, activeSeg, getCaptionAtY, onSegmentChange]);

  // Find the first and last caption indices in the active segment
  let inIdx = -1;
  let outIdx = -1;
  if (activeSeg) {
    for (let i = 0; i < captions.length; i++) {
      if (captions[i].end > activeSeg.start && captions[i].start < activeSeg.end) {
        if (inIdx === -1) inIdx = i;
        outIdx = i;
      }
    }
  }

  return (
    <div className="caption-panel caption-panel--single">
      {/* Segment info header */}
      {activeSeg && palette && (
        <div className="sidebar-segment-bar" style={{ borderLeftColor: palette.color }}>
          <span className="sidebar-segment-bar__dot" style={{ background: palette.color }} />
          <span className="sidebar-segment-bar__label">{activeSeg.label}</span>
          <span className="sidebar-segment-bar__range">
            {formatTime(activeSeg.start)} &mdash; {formatTime(activeSeg.end)}
          </span>
          <span className="sidebar-segment-bar__duration">
            {formatTime(activeSeg.end - activeSeg.start)}
          </span>
        </div>
      )}

      {/* Caption List */}
      <div className="caption-panel__section">
        <h3>Captions</h3>
        <div
          className="caption-panel__list"
          ref={listRef}
          style={{ cursor: dragging ? "ns-resize" : undefined }}
        >
          {captions.map((cap, i) => {
            const isActive = activeCaption === cap;
            const segColor = getColorForCaption(cap);
            const isInRange = i >= inIdx && i <= outIdx && activeSeg;
            const isInHandle = i === inIdx && activeSeg;
            const isOutHandle = i === outIdx && activeSeg;

            return (
              <div
                key={i}
                data-caption-index={i}
                className={[
                  "caption-item",
                  isActive ? "caption-item--active" : "",
                  isInRange ? "caption-item--in-range" : "",
                ].join(" ")}
                style={{
                  borderLeftColor: isActive
                    ? "#ffffff"
                    : segColor ?? "transparent",
                  backgroundColor: isInRange
                    ? isActive ? `${palette?.color}30` : `${palette?.color}10`
                    : isActive ? "rgba(255,255,255,0.08)" : undefined,
                }}
                onClick={() => onSeek(cap.start)}
              >
                {/* In handle */}
                {isInHandle && palette && (
                  <div
                    className="caption-handle caption-handle--in"
                    style={{ background: palette.color }}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDragging("in");
                    }}
                    title="Drag to set clip start"
                  >
                    <span className="caption-handle__label">IN</span>
                  </div>
                )}
                {/* Out handle */}
                {isOutHandle && palette && (
                  <div
                    className="caption-handle caption-handle--out"
                    style={{ background: palette.color }}
                    onMouseDown={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setDragging("out");
                    }}
                    title="Drag to set clip end"
                  >
                    <span className="caption-handle__label">OUT</span>
                  </div>
                )}
                <span className="caption-item__time">
                  {formatTimePrecise(cap.start)}
                </span>
                <span className="caption-item__text">{cap.text}</span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
