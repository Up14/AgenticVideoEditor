import type { RefObject } from "react";

interface Props {
  videoRef: RefObject<HTMLVideoElement | null>;
  src: string;
  onLoadedMetadata: () => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
  currentTime: number;
  duration: number;
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
 * Video player component wrapping the HTML5 <video> element
 * with custom controls.
 */
export default function VideoPlayer({
  videoRef,
  src,
  onLoadedMetadata,
  isPlaying,
  onTogglePlay,
  currentTime,
  duration,
}: Props) {
  return (
    <div className="video-player">
      <video
        ref={videoRef}
        src={src}
        onLoadedMetadata={onLoadedMetadata}
        onClick={onTogglePlay}
        preload="metadata"
      />
      <div className="video-player__controls">
        <button className="play-btn" onClick={onTogglePlay}>
          {isPlaying ? "⏸" : "▶"}
        </button>
        <span className="time-display">
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>
      </div>
    </div>
  );
}
