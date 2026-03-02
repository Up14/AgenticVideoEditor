"""
output_builder.py
─────────────────
Aggregates results from all analyzers into the final structured JSON report.

Public API
----------
build_report(video_meta, style_results, anim_results, cut_results, segments) -> dict
"""

from __future__ import annotations
from style_analyzer    import StyleAnalyzer, StyleResult
from animation_analyzer import AnimationAnalyzer, AnimResult
from caption_tracker   import CaptionSegment
import numpy as np


def build_report(
    video_meta:    dict,
    style_results: list[StyleResult],
    anim_results:  list[AnimResult],
    cut_results:   dict,
    segments:      list[CaptionSegment],
    sample_fps:    float,
    static_text:   list[CaptionSegment] | None = None,
) -> dict:
    """
    Merge all per-segment analysis results into a single report dictionary.

    Parameters
    ----------
    video_meta    : output of frame_extractor.get_video_meta()
    style_results : list of StyleResult (one per segment)
    anim_results  : list of AnimResult  (one per segment)
    cut_results   : output of CutDetector.get_results()
    segments      : list of CaptionSegment
    sample_fps    : the FPS used during extraction
    """

    # ── 1. Video metadata ────────────────────────────────────────────────────
    meta_section = {
        "duration_sec":          video_meta.get("duration_sec"),
        "native_fps":            video_meta.get("native_fps"),
        "width":                 video_meta.get("width"),
        "height":                video_meta.get("height"),
        "sample_fps_used":       sample_fps,
        "total_captions_found":  len(segments),
    }

    # ── 2. Aggregated caption style ──────────────────────────────────────────
    style_section = StyleAnalyzer.aggregate(style_results) if style_results else {}

    # ── 3. Aggregated animation pattern ─────────────────────────────────────
    anim_section = AnimationAnalyzer.aggregate(anim_results) if anim_results else {}

    # ── 4. Editing style (cuts + zooms) ─────────────────────────────────────
    editing_section = {
        "cut_count":            cut_results.get("cut_count", 0),
        "avg_cut_interval_sec": cut_results.get("avg_cut_interval_sec"),
        "cut_timestamps":       cut_results.get("cut_timestamps", []),
        "zoom_event_count":     cut_results.get("zoom_event_count", 0),
        "zoom_events":          cut_results.get("zoom_events", []),
    }

    # ── 5. Per-segment detail (timeline) ────────────────────────────────────
    timeline = []
    karaoke_highlights = []
    for i, seg in enumerate(segments):
        entry = seg.to_dict()
        if i < len(style_results):
            entry["style"] = style_results[i].to_dict()
        if i < len(anim_results):
            entry["animation"] = anim_results[i].to_dict()

        # Karaoke highlight metadata
        if getattr(seg, "_karaoke_highlight", False):
            entry["karaoke_highlight"]       = True
            entry["karaoke_highlight_color"] = getattr(seg, "_karaoke_highlight_color", "")
            entry["karaoke_parent_caption"]  = getattr(seg, "_karaoke_parent_text", "")
            karaoke_highlights.append(entry)
        else:
            entry["karaoke_highlight"] = False

        timeline.append(entry)

    # ── 7. Filtered static overlays (for transparency) ──────────────────────
    static_section = []
    for seg in (static_text or []):
        d = seg.to_dict()
        d["filter_reason"] = getattr(seg, "_static_reason", "unknown")
        static_section.append(d)

    # ── 6. Style DNA summary card ────────────────────────────────────────────
    summary = _build_summary(style_section, anim_section, editing_section, meta_section)

    # Surface karaoke pattern in style_dna
    if karaoke_highlights:
        summary["karaoke_style"]           = True
        summary["karaoke_highlight_color"] = karaoke_highlights[0]["karaoke_highlight_color"]
        summary["karaoke_word_count"]      = len(karaoke_highlights)
    else:
        summary["karaoke_style"] = False

    return {
        "video_meta":               meta_section,
        "style_dna":                summary,
        "caption_style":            style_section,
        "animation_pattern":        anim_section,
        "editing_style":            editing_section,
        "caption_timeline":         timeline,
        "karaoke_highlights":       karaoke_highlights,   # dedicated karaoke list
        "filtered_static_overlays": static_section,
    }


def _build_summary(
    style:   dict,
    anim:    dict,
    editing: dict,
    meta:    dict,
) -> dict:
    """
    Build the top-level "style DNA" card — the compact one-glance JSON
    that describes the viral template.
    """
    font_size_label = "small"
    avg_px = style.get("avg_font_size_px", 0)
    vid_h  = meta.get("height", 720)
    if avg_px / max(vid_h, 1) > 0.12:
        font_size_label = "large"
    elif avg_px / max(vid_h, 1) > 0.07:
        font_size_label = "medium"

    cut_interval = editing.get("avg_cut_interval_sec")
    pace = "slow"
    if cut_interval is not None:
        if cut_interval < 2.0:
            pace = "fast"
        elif cut_interval < 4.0:
            pace = "medium"

    return {
        "font_color":        style.get("dominant_font_color", "#FFFFFF"),
        "font_size_px":      style.get("avg_font_size_px"),
        "font_size_label":   font_size_label,
        "font_weight":       style.get("font_weight", "unknown"),
        "font_family":       style.get("font_family", "unknown"),
        "stroke":            style.get("has_stroke", False),
        "stroke_color":      style.get("stroke_color", "#000000"),
        "shadow":            style.get("has_shadow", False),
        "caption_position":  style.get("position_pattern", "unknown"),
        "background":        style.get("background_style", "none"),
        "entry_animation":   anim.get("entry_animation", "static"),
        "exit_animation":    anim.get("exit_animation", "static"),
        "word_by_word":      anim.get("word_by_word", False),
        "cut_frequency":     f"every {cut_interval}s" if cut_interval else "N/A",
        "editing_pace":      pace,
        "zoom_events":       editing.get("zoom_event_count", 0),
    }
