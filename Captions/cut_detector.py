"""
cut_detector.py
───────────────
Detects scene cuts and zoom events in a video by analysing frame-to-frame
visual differences.

Public API
----------
CutDetector(cut_threshold, zoom_threshold)
    .process_frame(frame_idx, timestamp, frame_bgr)  -> None
    .get_results()                                    -> dict
"""

from __future__ import annotations
import cv2
import numpy as np
from dataclasses import dataclass, field


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _hsv_histogram(frame_bgr: np.ndarray, bins: int = 32) -> np.ndarray:
    """Compute a flattened, normalised HSV histogram for *frame_bgr*."""
    hsv  = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1, 2], None,
                        [bins, bins, bins],
                        [0, 180, 0, 256, 0, 256])
    cv2.normalize(hist, hist)
    return hist.flatten()


def _chi_squared(h1: np.ndarray, h2: np.ndarray) -> float:
    """Chi-squared distance between two histograms (lower = more similar)."""
    eps  = 1e-10
    diff = h1 - h2
    chi  = np.sum(diff ** 2 / (h1 + h2 + eps))
    return float(chi)


def _optical_flow_magnitude(
    prev_gray: np.ndarray,
    curr_gray: np.ndarray,
) -> float:
    """Mean optical flow magnitude between two grayscale frames."""
    try:
        flow = cv2.calcOpticalFlowFarneback(
            prev_gray, curr_gray, None,
            pyr_scale=0.5, levels=2, winsize=15,
            iterations=2, poly_n=5, poly_sigma=1.1, flags=0,
        )
        mag, _ = cv2.cartToPolar(flow[..., 0], flow[..., 1])
        return float(np.mean(mag))
    except Exception:
        return 0.0


# ──────────────────────────────────────────────────────────────────────────────
# Detector
# ──────────────────────────────────────────────────────────────────────────────

class CutDetector:
    """
    Feed frames one-by-one with *process_frame*.
    After the last frame call *get_results* for the aggregated report.
    """

    def __init__(
        self,
        cut_threshold:  float = 0.35,   # chi-squared distance → cut
        zoom_threshold: float = 2.0,    # mean optical flow magnitude → zoom
        zoom_min_frames: int  = 3,      # consecutive frames above threshold to call a zoom
    ):
        self._cut_thr   = cut_threshold
        self._zoom_thr  = zoom_threshold
        self._zoom_min  = zoom_min_frames

        self._prev_hist: np.ndarray | None = None
        self._prev_gray: np.ndarray | None = None

        self._cuts: list[float] = []          # timestamps of detected cuts
        self._flow_ts: list[tuple] = []       # (timestamp, flow_mag)

        self._zoom_buffer: list[tuple] = []   # accumulation of (ts, mag)
        self._zoom_events: list[dict] = []

    # ── public ──────────────────────────────────────────────────────────────

    def process_frame(
        self,
        frame_idx:  int,
        timestamp:  float,
        frame_bgr:  np.ndarray,
    ) -> None:
        curr_hist = _hsv_histogram(frame_bgr)
        curr_gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)

        # ── Cut detection ────────────────────────────────────────────────────
        if self._prev_hist is not None:
            dist = _chi_squared(self._prev_hist, curr_hist)
            if dist > self._cut_thr:
                self._cuts.append(timestamp)
                # Reset zoom buffer on a cut
                self._flush_zoom_buffer()

            # ── Zoom detection (optical flow on non-cut frames) ──────────────
            else:
                if self._prev_gray is not None:
                    mag = _optical_flow_magnitude(self._prev_gray, curr_gray)
                    self._flow_ts.append((timestamp, mag))
                    if mag > self._zoom_thr:
                        self._zoom_buffer.append((timestamp, mag))
                    else:
                        self._flush_zoom_buffer()

        self._prev_hist = curr_hist
        self._prev_gray = curr_gray

    def get_results(self) -> dict:
        """Return aggregated cut + zoom statistics."""
        self._flush_zoom_buffer()   # close any open zoom at end of video

        cut_count = len(self._cuts)
        if cut_count >= 2:
            intervals            = [self._cuts[i+1] - self._cuts[i] for i in range(cut_count - 1)]
            avg_cut_interval_sec = round(float(np.mean(intervals)), 2)
        elif cut_count == 1:
            avg_cut_interval_sec = None
        else:
            avg_cut_interval_sec = None

        return {
            "cut_timestamps":        [round(t, 2) for t in self._cuts],
            "cut_count":             cut_count,
            "avg_cut_interval_sec":  avg_cut_interval_sec,
            "zoom_events":           self._zoom_events,
            "zoom_event_count":      len(self._zoom_events),
        }

    # ── private ─────────────────────────────────────────────────────────────

    def _flush_zoom_buffer(self) -> None:
        """Convert the accumulated zoom buffer into a ZoomEvent if long enough."""
        if len(self._zoom_buffer) >= self._zoom_min:
            ts_list  = [t for t, _ in self._zoom_buffer]
            mag_list = [m for _, m in self._zoom_buffer]
            self._zoom_events.append({
                "start": round(ts_list[0],  2),
                "end":   round(ts_list[-1], 2),
                "type":  "zoom_in",   # Farneback can't reliably distinguish in/out without
                                      # tracking a reference point, so we label all as zoom_in
                                      # for Phase A.
                "avg_magnitude": round(float(np.mean(mag_list)), 3),
            })
        self._zoom_buffer = []
