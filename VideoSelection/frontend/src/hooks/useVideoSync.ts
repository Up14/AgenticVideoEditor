import { useState, useCallback, useRef, useEffect } from "react";

/**
 * Hook to synchronize the video player's currentTime with the timeline
 * and other components. Provides a shared playback state.
 */
export function useVideoSync() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);

  // Update currentTime every animation frame for smooth sync
  useEffect(() => {
    let animationFrameId: number;

    const update = () => {
      const video = videoRef.current;
      if (video) {
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

  const togglePlay = useCallback(() => {
    const video = videoRef.current;
    if (!video) return;
    if (video.paused) {
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
