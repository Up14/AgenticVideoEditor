import { useRef, useEffect } from "react";
import type { Caption } from "../api/client";
import type { Segment } from "../types";
import { getSegmentColor, formatTimePrecise } from "../types";

interface Props {
  captions: Caption[];
  segments: Segment[];
  activeCaption: Caption | null;
  activeCaptionIndex: number;
  onSeek: (time: number) => void;
}

/**
 * Single caption list — captions are color-coded by the segment they belong to.
 * If a caption falls in multiple segments, the first matching segment's color wins.
 */
export default function CaptionPanel({
  captions,
  segments,
  activeCaption,
  activeCaptionIndex,
  onSeek,
}: Props) {
  const listRef = useRef<HTMLDivElement>(null);

  // Auto-scroll within the caption list only (never scrolls the page)
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

  /**
   * Find the segment color for a caption. Returns the first matching
   * segment's color, or null if the caption isn't in any segment.
   */
  const getColorForCaption = (cap: Caption): string | null => {
    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      if (cap.end > seg.start && cap.start < seg.end) {
        return getSegmentColor(i).color;
      }
    }
    return null;
  };

  return (
    <div className="caption-panel caption-panel--single">
      <div className="caption-panel__section">
        <h3>📄 Video Captions</h3>
        <div className="caption-panel__list" ref={listRef}>
          {captions.map((cap, i) => {
            const isActive = activeCaption === cap;
            const segColor = getColorForCaption(cap);

            return (
              <div
                key={i}
                data-caption-index={i}
                className={[
                  "caption-item",
                  isActive ? "caption-item--active" : "",
                  segColor ? "caption-item--in-segment" : "",
                ].join(" ")}
                style={{
                  borderLeftColor: isActive
                    ? "#ffffff"
                    : segColor ?? "transparent",
                  backgroundColor: segColor
                    ? isActive ? `${segColor}30` : `${segColor}10`
                    : isActive ? "rgba(255,255,255,0.08)" : undefined,
                }}
                onClick={() => onSeek(cap.start)}
              >
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
