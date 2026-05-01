"""
animation_analyzer.py
─────────────────────
Detects how captions animate in and out by comparing bounding box
properties across the first/last few frames of each CaptionSegment.

Public API
----------
AnimationAnalyzer.analyze(segment)   -> AnimResult
AnimationAnalyzer.aggregate(results) -> dict
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass
from caption_tracker import CaptionSegment

# Minimum number of frames a segment must span to detect animation
_MIN_FRAMES_FOR_ANIM = 3


@dataclass
class AnimResult:
    segment_text:      str
    entry_animation:   str    # pop_in | slide_left | slide_right | slide_up | fade_in | word_by_word | static
    exit_animation:    str    # pop_out | slide_out | fade_out | static
    is_word_by_word:   bool
    anim_entry_frames: int    # how many frames the entry animation spans

    def to_dict(self) -> dict:
        return {
            "text":              self.segment_text[:60],
            "entry_animation":   self.entry_animation,
            "exit_animation":    self.exit_animation,
            "word_by_word":      self.is_word_by_word,
            "entry_frames":      self.anim_entry_frames,
        }


class AnimationAnalyzer:

    @staticmethod
    def analyze(segment: CaptionSegment) -> AnimResult:
        bboxes = segment.bbox_series   # list of (x, y, w, h)
        confs  = segment.conf_series

        n = len(bboxes)

        # Default — static
        entry = "static"
        exit_ = "static"
        wbw   = False
        entry_frames = 0

        if n < _MIN_FRAMES_FOR_ANIM:
            return AnimResult(
                segment_text      = segment.text,
                entry_animation   = entry,
                exit_animation    = exit_,
                is_word_by_word   = wbw,
                anim_entry_frames = entry_frames,
            )

        # ── Word-by-word detection ───────────────────────────────────────────
        # Text length grows across consecutive frames that share the same
        # approximate bounding box center.
        # We approximate by checking if conf_series grows noticeably in early
        # frames (proxy for progressive text reveal in OCR confidence).
        # A more direct check: compare width growth.
        widths = [b[2] for b in bboxes]
        early  = widths[:max(2, n // 3)]
        if len(early) >= 2:
            width_growth = (early[-1] - early[0]) / max(early[0], 1)
            if width_growth > 0.25:
                wbw = True

        # ── Entry animation detection (first 3–5 frames) ─────────────────────
        window = min(5, n // 2, n - 1)
        if window >= 1:
            first_bbox = bboxes[0]
            mid_bbox   = bboxes[window]

            # Area change → scale / pop-in
            area_first = first_bbox[2] * first_bbox[3]
            area_mid   = mid_bbox[2]   * mid_bbox[3]
            area_ratio = area_mid / max(area_first, 1)

            # Position shift → slide
            dx = mid_bbox[0] - first_bbox[0]   # horizontal shift
            dy = mid_bbox[1] - first_bbox[1]   # vertical shift

            # Confidence ramp → fade-in
            conf_ramp = False
            if len(confs) > window:
                conf_ramp = (confs[window] - confs[0]) > 0.15

            if wbw:
                entry = "word_by_word"
                entry_frames = n
            elif area_ratio > 1.30:
                entry = "pop_in"
                entry_frames = window
            elif abs(dx) > 20 and abs(dx) > abs(dy):
                entry = "slide_left" if dx < 0 else "slide_right"
                entry_frames = window
            elif abs(dy) > 20:
                entry = "slide_up" if dy < 0 else "slide_down"
                entry_frames = window
            elif conf_ramp:
                entry = "fade_in"
                entry_frames = window

        # ── Exit animation detection (last 3–5 frames) ───────────────────────
        if window >= 1:
            last_bbox = bboxes[-1]
            pre_bbox  = bboxes[-(window + 1)]

            area_pre  = pre_bbox[2]  * pre_bbox[3]
            area_last = last_bbox[2] * last_bbox[3]
            area_ratio_exit = area_last / max(area_pre, 1)

            dx_exit = last_bbox[0] - pre_bbox[0]
            dy_exit = last_bbox[1] - pre_bbox[1]

            conf_drop = False
            if len(confs) > window:
                conf_drop = (confs[-(window + 1)] - confs[-1]) > 0.15

            if area_ratio_exit < 0.70:
                exit_ = "pop_out"
            elif abs(dx_exit) > 20:
                exit_ = "slide_out"
            elif abs(dy_exit) > 20:
                exit_ = "slide_out"
            elif conf_drop:
                exit_ = "fade_out"

        return AnimResult(
            segment_text      = segment.text,
            entry_animation   = entry,
            exit_animation    = exit_,
            is_word_by_word   = wbw,
            anim_entry_frames = entry_frames,
        )

    @staticmethod
    def aggregate(results: list[AnimResult]) -> dict:
        if not results:
            return {}

        def _most_common(values: list) -> str:
            counts: dict = {}
            for v in values:
                counts[v] = counts.get(v, 0) + 1
            return max(counts, key=counts.get) if counts else "static"

        dominant_entry = _most_common([r.entry_animation for r in results])
        dominant_exit  = _most_common([r.exit_animation  for r in results])
        wbw_pct        = sum(r.is_word_by_word for r in results) / len(results)

        return {
            "entry_animation": dominant_entry,
            "exit_animation":  dominant_exit,
            "word_by_word":    wbw_pct > 0.4,
            "caption_count":   len(results),
        }
