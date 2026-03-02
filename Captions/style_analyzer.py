"""
style_analyzer.py
─────────────────
Extracts visual styling properties from a CaptionSegment by analysing the
pixels inside the text bounding box.

Public API
----------
StyleAnalyzer(video_frames_cache)
    .analyze(segment, frame_bgr, video_h, video_w) -> StyleResult
    .aggregate(style_results)                       -> dict  (summary for whole video)
"""

from __future__ import annotations
import numpy as np
import cv2
from dataclasses import dataclass
from caption_tracker import CaptionSegment
from font_recognizer import FontRecognizer

# Module-level shared recognizer instance (lazy-loads on first use)
_font_recognizer = FontRecognizer()


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _bgr_to_hex(bgr: tuple) -> str:
    b, g, r = int(bgr[0]), int(bgr[1]), int(bgr[2])
    return f"#{r:02X}{g:02X}{b:02X}"


def is_brand_color(hex_color: str) -> bool:
    """
    Return True if *hex_color* is in the orange/amber hue band that typically
    indicates a brand watermark overlay (e.g. CAGEI / THE / IHB).

    Orange HSV range: hue 8–28° (OpenCV 0-180 scale → 4–14),
    saturation > 120, value > 100.
    """
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return False

    # Convert to HSV using OpenCV conventions
    bgr_pixel = np.array([[[b, g, r]]], dtype=np.uint8)
    hsv = cv2.cvtColor(bgr_pixel, cv2.COLOR_BGR2HSV)[0, 0]
    hue, sat, val = int(hsv[0]), int(hsv[1]), int(hsv[2])

    # OpenCV hue: 0-180.  Orange ≈ 8-28° → scale 4-14
    return (4 <= hue <= 14) and sat > 120 and val > 100


def _dominant_color(patch: np.ndarray, k: int = 2) -> tuple:
    """K-means dominant color — returns the BRIGHTEST cluster (most likely text)."""
    if patch.size == 0:
        return (255, 255, 255)
    pixels = patch.reshape(-1, 3).astype(np.float32)
    if len(pixels) < k:
        return tuple(int(v) for v in pixels[0])
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 10, 1.0)
    _, labels, centers = cv2.kmeans(
        pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    # Pick the BRIGHTEST cluster — text is almost always lighter than background
    brightness = np.mean(centers, axis=1)  # average BGR brightness per cluster
    dominant = centers[np.argmax(brightness)]
    return tuple(int(v) for v in dominant)


def _text_color(patch: np.ndarray) -> tuple:
    """
    More accurate text-color extraction:
    1. Convert to grayscale and threshold to isolate bright pixels (text).
    2. Sample the mean BGR of those pixels.
    3. Fall back to brightest K-means cluster if fewer than 50 bright pixels.
    """
    if patch.size == 0 or patch.shape[0] < 4 or patch.shape[1] < 4:
        return (255, 255, 255)

    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)

    # Adaptive threshold: pick pixels brighter than 60th percentile
    threshold = max(float(np.percentile(gray, 60)), 100.0)
    mask = gray >= threshold

    bright_pixels = patch[mask]
    if len(bright_pixels) >= 50:
        mean_bgr = np.mean(bright_pixels, axis=0)
        return tuple(int(v) for v in mean_bgr)

    # Fallback: brightest K-means cluster
    return _dominant_color(patch, k=2)


def _classify_position(cx: int, cy: int, w: int, h: int) -> str:
    """Return a human label like 'bottom_center' for the bounding box."""
    horiz = "left" if cx < w * 0.33 else ("right" if cx > w * 0.67 else "center")
    vert  = "top"  if cy < h * 0.33 else ("bottom" if cy > h * 0.67 else "middle")
    return f"{vert}_{horiz}"


def _has_stroke(patch: np.ndarray) -> bool:
    """
    Heuristic: detect a stroke around the text by checking if there is a dark
    border ring around the lighter text blob.
    """
    if patch.size == 0 or patch.shape[0] < 6 or patch.shape[1] < 6:
        return False
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    # Erode to shrink text inward, compare edges
    kernel  = np.ones((3, 3), np.uint8)
    eroded  = cv2.erode(gray, kernel, iterations=1)
    border  = cv2.absdiff(gray, eroded)
    # High variance in the border region suggests a colored stroke
    return bool(np.std(border) > 12)


def _stroke_color(patch: np.ndarray) -> tuple:
    """Sample the ~3px border ring around the patch for stroke color."""
    if patch.size == 0 or patch.shape[0] < 8 or patch.shape[1] < 8:
        return (0, 0, 0)
    border_mask = np.zeros(patch.shape[:2], dtype=np.uint8)
    border_mask[:3,  :]  = 255
    border_mask[-3:, :]  = 255
    border_mask[:,  :3]  = 255
    border_mask[:, -3:]  = 255
    border_pixels = patch[border_mask == 255]
    if len(border_pixels) == 0:
        return (0, 0, 0)
    return _dominant_color(border_pixels, k=1)


def _has_shadow(patch: np.ndarray) -> bool:
    """
    Check for a drop shadow by comparing the mean brightness in the bottom 20%
    vs the top 80% — a significantly darker bottom suggests a drop shadow.
    """
    if patch.size == 0 or patch.shape[0] < 10:
        return False
    split = int(patch.shape[0] * 0.80)
    top_mean    = np.mean(cv2.cvtColor(patch[:split, :],  cv2.COLOR_BGR2GRAY))
    bottom_mean = np.mean(cv2.cvtColor(patch[split:, :],  cv2.COLOR_BGR2GRAY))
    # Shadow: bottom noticeably darker AND bottom itself is dark
    return bool(bottom_mean < top_mean * 0.70 and bottom_mean < 100)


def _background_style(patch: np.ndarray) -> str:
    """Classify the background behind the text patch."""
    if patch.size == 0:
        return "none"
    gray = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    std  = np.std(gray)
    mean = np.mean(gray)
    if std < 15:
        return "solid_box"
    if std < 40 and mean < 80:
        return "blur"
    return "none"


def _estimate_font_weight(patch: np.ndarray) -> str:
    """
    Estimate bold vs regular by measuring average stroke width via
    morphological closing.
    """
    if patch.size == 0:
        return "unknown"
    gray    = cv2.cvtColor(patch, cv2.COLOR_BGR2GRAY)
    _, bw   = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    kernel  = np.ones((3, 3), np.uint8)
    closed  = cv2.morphologyEx(bw, cv2.MORPH_CLOSE, kernel)
    ratio   = np.sum(closed > 0) / closed.size if closed.size > 0 else 0
    return "bold" if ratio > 0.45 else "regular"


# ──────────────────────────────────────────────────────────────────────────────
# Result dataclass
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class StyleResult:
    segment_text:            str
    font_color_bgr:          tuple
    font_color_hex:          str
    font_size_px:            int
    font_size_relative:      float
    font_weight:             str
    position_label:          str
    position_norm:           dict   # {x: 0-1, y: 0-1}
    has_stroke:              bool
    stroke_color_hex:        str
    has_shadow:              bool
    background_style:        str
    font_family:             str    = "unknown"
    font_family_confidence:  float  = 0.0
    font_family_top3:        list   = None

    def to_dict(self) -> dict:
        return {
            "text":                   self.segment_text[:60],
            "font_color":             self.font_color_hex,
            "font_size_px":           self.font_size_px,
            "font_size_relative":     round(self.font_size_relative, 3),
            "font_weight":            self.font_weight,
            "font_family":            self.font_family,
            "font_family_confidence": self.font_family_confidence,
            "font_family_top3":       self.font_family_top3 or [],
            "position":               self.position_label,
            "position_norm":          {k: round(v, 3) for k, v in self.position_norm.items()},
            "has_stroke":             self.has_stroke,
            "stroke_color":           self.stroke_color_hex,
            "has_shadow":             self.has_shadow,
            "background_style":       self.background_style,
        }


# ──────────────────────────────────────────────────────────────────────────────
# Main analyzer
# ──────────────────────────────────────────────────────────────────────────────

class StyleAnalyzer:

    @staticmethod
    def analyze(
        segment:   CaptionSegment,
        frame_bgr: np.ndarray,
        video_h:   int,
        video_w:   int,
    ) -> StyleResult:
        """
        Analyze styling for *segment* using the representative frame *frame_bgr*.
        """
        rb = segment.representative_bbox()
        if rb is None:
            x, y, w, h = 0, 0, 32, 32
        else:
            x, y, w, h = rb

        # Clamp to frame dimensions
        x  = max(0, x)
        y  = max(0, y)
        x2 = min(frame_bgr.shape[1], x + w)
        y2 = min(frame_bgr.shape[0], y + h)
        patch = frame_bgr[y:y2, x:x2]

        cx = x + w // 2
        cy = y + h // 2

        color_bgr   = _text_color(patch)
        stroke      = _has_stroke(patch)
        s_color_bgr = _stroke_color(patch) if stroke else (0, 0, 0)

        # Font family recognition
        font_info = _font_recognizer.recognize(patch)

        return StyleResult(
            segment_text             = segment.text,
            font_color_bgr           = color_bgr,
            font_color_hex           = _bgr_to_hex(color_bgr),
            font_size_px             = h,
            font_size_relative       = h / video_h if video_h > 0 else 0.0,
            font_weight              = _estimate_font_weight(patch),
            position_label           = _classify_position(cx, cy, video_w, video_h),
            position_norm            = {"x": cx / video_w, "y": cy / video_h},
            has_stroke               = stroke,
            stroke_color_hex         = _bgr_to_hex(s_color_bgr),
            has_shadow               = _has_shadow(patch),
            background_style         = _background_style(patch),
            font_family              = font_info["font_family"],
            font_family_confidence   = font_info["confidence"],
            font_family_top3         = font_info["top3"],
        )

    @staticmethod
    def aggregate(results: list[StyleResult]) -> dict:
        """Summarize style results across all segments into a single style card."""
        if not results:
            return {}

        # Most common font color
        color_counts: dict = {}
        for r in results:
            color_counts[r.font_color_hex] = color_counts.get(r.font_color_hex, 0) + 1
        dominant_color = max(color_counts, key=color_counts.get)

        # Most common position
        pos_counts: dict = {}
        for r in results:
            pos_counts[r.position_label] = pos_counts.get(r.position_label, 0) + 1
        dominant_pos = max(pos_counts, key=pos_counts.get)

        avg_size_px = int(np.mean([r.font_size_px for r in results]))

        weight_counts: dict = {}
        for r in results:
            weight_counts[r.font_weight] = weight_counts.get(r.font_weight, 0) + 1
        dominant_weight = max(weight_counts, key=weight_counts.get)

        has_stroke_pct = sum(r.has_stroke for r in results) / len(results)

        stroke_color = "#000000"
        if has_stroke_pct > 0.5:
            sc_counts: dict = {}
            for r in results:
                if r.has_stroke:
                    sc_counts[r.stroke_color_hex] = sc_counts.get(r.stroke_color_hex, 0) + 1
            if sc_counts:
                stroke_color = max(sc_counts, key=sc_counts.get)

        bg_counts: dict = {}
        for r in results:
            bg_counts[r.background_style] = bg_counts.get(r.background_style, 0) + 1
        dominant_bg = max(bg_counts, key=bg_counts.get)

        # Majority-vote font family
        dominant_font_family = FontRecognizer.aggregate(
            [r.font_family for r in results]
        )

        return {
            "dominant_font_color":  dominant_color,
            "avg_font_size_px":     avg_size_px,
            "font_weight":          dominant_weight,
            "font_family":          dominant_font_family,
            "position_pattern":     dominant_pos,
            "has_stroke":           has_stroke_pct > 0.5,
            "stroke_color":         stroke_color,
            "has_shadow":           sum(r.has_shadow for r in results) / len(results) > 0.4,
            "background_style":     dominant_bg,
        }
