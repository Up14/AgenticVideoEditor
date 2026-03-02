"""
caption_tracker.py
───────────────────
Tracks text boxes across video frames to build a timeline of caption appearances.

Uses IoU (Intersection-over-Union) + text similarity to match boxes between frames.

🔑 Key design: distinguishes TRUE captions (short duration, centre-screen) from
   STATIC OVERLAYS (watermarks, usernames, title cards) using three signals:
   1. Duration ratio  — segment lasts >35% of total video → watermark / title
   2. Corner position — top-left or top-right bbox → watermark location
   3. Text length     — single char / symbol → UI element, not caption

Public API
----------
CaptionTracker()
    .update(frame_idx, timestamp, text_boxes) -> None
    .flush(frame_idx, timestamp)              -> None
    .get_segments(video_duration)             -> list[CaptionSegment]  (true captions only)
    .get_static_text()                        -> list[CaptionSegment]  (watermarks / overlays)
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional
from text_detector import TextBox


# ──────────────────────────────────────────────────────────────────────────────
# Data structures
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class CaptionSegment:
    """A caption that appears+stays visible for multiple frames."""
    text:          str
    start_frame:   int
    end_frame:     int
    start_time:    float
    end_time:      float
    bbox_series:   list = field(default_factory=list)   # list of (x,y,w,h) per frame
    conf_series:   list = field(default_factory=list)   # confidence per frame

    def duration(self) -> float:
        return round(self.end_time - self.start_time, 3)

    def frame_count(self) -> int:
        return self.end_frame - self.start_frame + 1

    def representative_bbox(self):
        """Return the median bounding box across frames."""
        if not self.bbox_series:
            return None
        arr = np.array(self.bbox_series)
        return tuple(int(v) for v in np.median(arr, axis=0))

    def to_dict(self) -> dict:
        rb = self.representative_bbox()
        return {
            "text":       self.text,
            "start_time": self.start_time,
            "end_time":   self.end_time,
            "duration":   self.duration(),
            "bbox":       {"x": rb[0], "y": rb[1], "w": rb[2], "h": rb[3]} if rb else None,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Internal active-track state
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class _Track:
    text:        str
    start_frame: int
    start_time:  float
    last_frame:  int
    last_time:   float
    bbox_series: list = field(default_factory=list)
    conf_series: list = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# IoU + text helpers
# ──────────────────────────────────────────────────────────────────────────────

def _iou(a: tuple, b: tuple) -> float:
    """Compute IoU between two (x,y,w,h) boxes."""
    ax1, ay1 = a[0], a[1]
    ax2, ay2 = ax1 + a[2], ay1 + a[3]
    bx1, by1 = b[0], b[1]
    bx2, by2 = bx1 + b[2], by1 + b[3]

    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)

    inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
    if inter == 0:
        return 0.0

    union = a[2] * a[3] + b[2] * b[3] - inter
    return inter / union if union > 0 else 0.0


def _text_sim(a: str, b: str) -> float:
    """Simple character-level Jaccard similarity."""
    sa, sb = set(a.lower()), set(b.lower())
    if not sa and not sb:
        return 1.0
    return len(sa & sb) / len(sa | sb)


def _is_static_text(
    seg:           "CaptionSegment",
    video_duration: float,
    video_w:        int = 0,
    video_h:        int = 0,
    max_ratio:      float = 0.35,
) -> tuple[bool, str]:
    """
    Returns (is_static, reason) where is_static=True means this segment should
    be classified as a watermark / title card / UI overlay, NOT a rolling caption.

    Three-signal detection
    ─────────────────────
    1. Duration ratio  — if the segment is visible for >max_ratio of the video,
                         it is almost certainly a persistent overlay (watermark, username).
    2. Corner position — watermarks almost always live in a corner.  If the bbox
                         centre is in the outer 15% of width AND outer 20% of height
                         it is positionally a watermark.
    3. Symbol / junk   — segments whose text is shorter than 2 meaningful characters
                         are UI icons, bullets, or OCR noise.
    """
    # ── Signal 3: Too short to be a real caption ─────────────────────────────
    clean = seg.text.strip()
    if len(clean) <= 2:
        return True, "text_too_short"

    # ── Signal 1: Duration ratio ─────────────────────────────────────────────
    if video_duration > 0:
        ratio = seg.duration() / video_duration
        if ratio > max_ratio:
            return True, f"duration_ratio_{ratio:.2f}"

    # ── Signal 2: Corner position (only if we know frame dimensions) ─────────
    if video_w > 0 and video_h > 0 and seg.bbox_series:
        rb = seg.representative_bbox()
        if rb:
            cx = rb[0] + rb[2] // 2
            cy = rb[1] + rb[3] // 2
            in_corner_h = (cx < video_w * 0.15) or (cx > video_w * 0.85)
            in_corner_v = (cy < video_h * 0.20) or (cy > video_h * 0.80)
            # Only flag as watermark if BOTH corner conditions are met
            if in_corner_h and in_corner_v:
                return True, "corner_position"

    return False, ""


# ──────────────────────────────────────────────────────────────────────────────
# Tracker
# ──────────────────────────────────────────────────────────────────────────────

class CaptionTracker:
    """
    Matches newly detected text boxes to existing tracks using IoU + text
    similarity.  Tracks that aren't seen for *gap_tolerance* frames are closed
    and converted to CaptionSegments.
    """

    def __init__(
        self,
        iou_threshold:          float = 0.30,
        text_threshold:         float = 0.40,
        gap_tolerance:          int   = 3,
        min_frames:             int   = 2,
        max_static_ratio:       float = 0.35,   # >35% of video duration = static overlay
    ):
        self._iou_thr       = iou_threshold
        self._text_thr      = text_threshold
        self._gap           = gap_tolerance
        self._min_fr        = min_frames
        self._max_static    = max_static_ratio
        self._tracks: list[_Track] = []
        self._segments: list[CaptionSegment] = []
        # Stores filtered-out static overlays (watermarks, titles) separately
        self._static: list[CaptionSegment] = []

    # ── public ──────────────────────────────────────────────────────────────

    def update(
        self,
        frame_idx:  int,
        timestamp:  float,
        text_boxes: list[TextBox],
    ) -> None:
        """Feed detections from one frame into the tracker."""
        new_boxes = [(b.x, b.y, b.w, b.h) for b in text_boxes]
        matched_tracks = set()
        matched_boxes  = set()

        # ── Match boxes to existing tracks ──────────────────────────────────
        for ti, track in enumerate(self._tracks):
            if not track.bbox_series:
                continue
            last_bbox = track.bbox_series[-1]

            best_score, best_bi = -1.0, -1
            for bi, (box, tb) in enumerate(zip(new_boxes, text_boxes)):
                if bi in matched_boxes:
                    continue
                iou  = _iou(last_bbox, box)
                tsim = _text_sim(track.text, tb.text)
                score = iou * 0.6 + tsim * 0.4
                if score > best_score:
                    best_score, best_bi = score, bi

            if best_score >= (self._iou_thr * 0.6 + self._text_thr * 0.4) and best_bi >= 0:
                tb = text_boxes[best_bi]
                track.last_frame = frame_idx
                track.last_time  = timestamp
                track.bbox_series.append(new_boxes[best_bi])
                track.conf_series.append(tb.confidence)
                # Update text to latest (captures word-by-word growth)
                track.text = tb.text
                matched_tracks.add(ti)
                matched_boxes.add(best_bi)

        # ── Close stale tracks ───────────────────────────────────────────────
        still_active = []
        for ti, track in enumerate(self._tracks):
            if ti in matched_tracks or (frame_idx - track.last_frame) <= self._gap:
                still_active.append(track)
            else:
                self._close_track(track)
        self._tracks = still_active

        # ── Start new tracks for unmatched boxes ─────────────────────────────
        for bi, (box, tb) in enumerate(zip(new_boxes, text_boxes)):
            if bi not in matched_boxes:
                self._tracks.append(_Track(
                    text        = tb.text,
                    start_frame = frame_idx,
                    start_time  = timestamp,
                    last_frame  = frame_idx,
                    last_time   = timestamp,
                    bbox_series = [box],
                    conf_series = [tb.confidence],
                ))

    def flush(self, frame_idx: int, timestamp: float) -> None:
        """Call after the last frame to close all remaining tracks."""
        for track in self._tracks:
            self._close_track(track)
        self._tracks = []

    def get_segments(
        self,
        video_duration: float = 0.0,
        video_w: int = 0,
        video_h: int = 0,
    ) -> list[CaptionSegment]:
        """
        Return only TRUE rolling captions, with static text filtered out.

        Parameters
        ----------
        video_duration : total video length in seconds (from get_video_meta)
        video_w, video_h : frame dimensions for corner-position check
        """
        # Re-run the filter each time (video_duration may not be known at close time)
        captions = []
        static   = []
        for seg in self._segments:
            is_static, reason = _is_static_text(
                seg, video_duration, video_w, video_h, self._max_static
            )
            if is_static:
                seg._static_reason = reason   # tag for transparency
                static.append(seg)
            else:
                captions.append(seg)
        self._static = static
        return sorted(captions, key=lambda s: s.start_time)

    def get_static_text(self) -> list[CaptionSegment]:
        """
        Return the segments that were classified as static overlays
        (watermarks, usernames, title cards).  Call AFTER get_segments().
        """
        return sorted(self._static, key=lambda s: s.start_time)

    # ── private ─────────────────────────────────────────────────────────────

    def _close_track(self, track: _Track) -> None:
        if len(track.bbox_series) < self._min_fr:
            return
        self._segments.append(CaptionSegment(
            text        = track.text,
            start_frame = track.start_frame,
            end_frame   = track.last_frame,
            start_time  = track.start_time,
            end_time    = track.last_time,
            bbox_series = track.bbox_series,
            conf_series = track.conf_series,
        ))
