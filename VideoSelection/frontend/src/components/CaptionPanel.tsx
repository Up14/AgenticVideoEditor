import { useRef, useEffect } from "react";
import type { Caption } from "../api/client";

interface Props {
  captions: Caption[];
  selectedCaptions: Caption[];
  activeCaption: Caption | null;
  activeCaptionIndex: number;
  selectionStart: number;
  selectionEnd: number;
  onSeek: (time: number) => void;
}

/**
 * Formats seconds to MM:SS.s display.
 */
function formatTime(seconds: number): string {
  const m = Math.floor(seconds / 60);
  const s = (seconds % 60).toFixed(1);
  return `${m}:${parseFloat(s) < 10 ? "0" : ""}${s}`;
}

/**
 * Caption panel with two sections:
 * 1. Full timeline captions (scrolls to active)
 * 2. Selected region captions (green highlight)
 */
export default function CaptionPanel({
  captions,
  selectedCaptions,
  activeCaption,
  activeCaptionIndex,
  selectionStart,
  selectionEnd,
  onSeek,
}: Props) {
  const fullListRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to active caption
  useEffect(() => {
    if (activeCaptionIndex >= 0 && fullListRef.current) {
      const activeEl = fullListRef.current.querySelector(
        `[data-caption-index="${activeCaptionIndex}"]`
      );
      activeEl?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
  }, [activeCaptionIndex]);

  return (
    <div className="caption-panel">
      {/* Section 1: Full captions */}
      <div className="caption-panel__section">
        <h3>📄 Video Captions</h3>
        <div className="caption-panel__list" ref={fullListRef}>
          {captions.map((cap, i) => {
            const isActive = activeCaption === cap;
            const isInSelection =
              cap.end > selectionStart && cap.start < selectionEnd;

            return (
              <div
                key={i}
                data-caption-index={i}
                className={[
                  "caption-item",
                  isActive ? "caption-item--active" : "",
                  isInSelection ? "caption-item--in-selection" : "",
                ].join(" ")}
                onClick={() => onSeek(cap.start)}
              >
                <span className="caption-item__time">
                  {formatTime(cap.start)}
                </span>
                <span className="caption-item__text">{cap.text}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Section 2: Selected region captions */}
      <div className="caption-panel__section caption-panel__section--selected">
        <h3>
          🟢 Selected Clip Captions
          <span className="caption-count">
            ({selectedCaptions.length} segments)
          </span>
        </h3>
        <div className="caption-panel__list">
          {selectedCaptions.length === 0 ? (
            <div className="caption-empty">
              No captions in selected region
            </div>
          ) : (
            selectedCaptions.map((cap, i) => (
              <div
                key={i}
                className="caption-item caption-item--selected"
                onClick={() => onSeek(cap.start)}
              >
                <span className="caption-item__time">
                  {formatTime(cap.start)}
                </span>
                <span className="caption-item__text">{cap.text}</span>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
