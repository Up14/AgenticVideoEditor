import { useMemo } from "react";
import type { Caption } from "../api/client";

/**
 * Hook for filtering and highlighting captions based on
 * the current playback position and selection range.
 */
export function useCaptions(
  captions: Caption[],
  currentTime: number,
  selectionStart: number,
  selectionEnd: number
) {
  /** Caption currently being spoken (highlighted in player). */
  const activeCaption = useMemo(() => {
    return captions.find(
      (c) => currentTime >= c.start && currentTime < c.end
    ) ?? null;
  }, [captions, currentTime]);

  /** Captions within the green selection region. */
  const selectedCaptions = useMemo(() => {
    return captions.filter(
      (c) => c.end > selectionStart && c.start < selectionEnd
    );
  }, [captions, selectionStart, selectionEnd]);

  /** Index of the active caption in the full list. */
  const activeCaptionIndex = useMemo(() => {
    if (!activeCaption) return -1;
    return captions.indexOf(activeCaption);
  }, [captions, activeCaption]);

  return {
    activeCaption,
    activeCaptionIndex,
    selectedCaptions,
  };
}
