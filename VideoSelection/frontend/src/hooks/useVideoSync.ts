import { useState, useCallback, useRef, useEffect } from "react";

/**
 * Hook to synchronize the video player's currentTime with the timeline.
 * Constrains playback to the active selection region (in/out points).
 */
export function useVideoSync(
  selectionStart: number,
  selectionEnd: number
) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  // Track selection bounds in a ref so the animation frame loop
  // always sees the latest values without re-creating the effect.
  const boundsRef = useRef({ start: selectionStart, end: selectionEnd });
  boundsRef.current = { start: selectionStart, end: selectionEnd };

  // Update currentTime every animation frame + clamp to selection
  useEffect(() => {
    let animationFrameId: number;

    const update = () => {
      const video = videoRef.current;
      if (video) {
        // If playback has passed the out-point, pause and clamp
        if (!video.paused && video.currentTime >= boundsRef.current.end) {
          video.pause();
          video.currentTime = boundsRef.current.end;
        }

        setCurrentTime(video.currentTime);
        setIsPlaying(!video.paused);
      }
      animationFrameId = requestAnimationFrame(update);
    };

    animationFrameId = requestAnimationFrame(update);
    return () => cancelAnimationFrame(animationFrameId);
  }, []);

  const handleLoadedMetadata = useCallback(() => {
    if (videoRef.current) {
      setDuration(videoRef.current.duration);
    }
  }, []);

  const seekTo = useCallback((time: number) => {
    if (videoRef.current) {
      videoRef.current.currentTime = time;
      setCurrentTime(time);
    }
  }, []);

  /**
   * Play/pause — if the playhead is outside the selection or at the
   * out-point, jump to the in-point before playing.
   */
  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;

    if (video.paused) {
      const { start, end } = boundsRef.current;
      // If playhead is outside or at end of selection, snap to start
      if (video.currentTime < start || video.currentTime >= end) {
        video.currentTime = start;
      }
      video.play();
    } else {
      video.pause();
    }
  }, []);

  return {
    videoRef,
    currentTime,
    duration,
    isPlaying,
    seekTo,
    togglePlay,
    handleLoadedMetadata,
  };
}
