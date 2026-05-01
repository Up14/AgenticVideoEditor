"""
app.py — AI Video Style Analyzer
=================================
Streamlit UI that accepts a local MP4 file, runs the full analysis pipeline,
and displays a structured visual style card + downloadable JSON report.
"""

from __future__ import annotations
import json
import os
import sys
import tempfile
import traceback

import cv2
import numpy as np
import streamlit as st

# Add the Captions directory to path so sibling modules resolve correctly
sys.path.insert(0, os.path.dirname(__file__))

from frame_extractor    import extract_frames, get_video_meta
from text_detector      import TextDetector
from caption_tracker    import CaptionTracker
from style_analyzer     import StyleAnalyzer, is_brand_color
from animation_analyzer import AnimationAnalyzer
from cut_detector       import CutDetector
from output_builder     import build_report

# ─────────────────────────────────────────────────────────────────────────────
# Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title = "AI Video Style Analyzer",
    page_icon  = "🎬",
    layout     = "wide",
)

# ─────────────────────────────────────────────────────────────────────────────
# Global CSS
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark gradient background */
.stApp {
    background: linear-gradient(135deg, #0d0d1a 0%, #111827 50%, #0d1117 100%);
    color: #e2e8f0;
}

/* Header hero */
.hero-title {
    font-size: 2.8rem;
    font-weight: 800;
    background: linear-gradient(90deg, #a78bfa, #60a5fa, #34d399);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    background-clip: text;
    line-height: 1.2;
    margin-bottom: 0.25rem;
}
.hero-sub {
    color: #94a3b8;
    font-size: 1.05rem;
    font-weight: 400;
    margin-bottom: 2rem;
}

/* DNA card */
.dna-card {
    background: linear-gradient(135deg, #1e1b4b 0%, #1a1a2e 100%);
    border: 1px solid #3730a3;
    border-radius: 16px;
    padding: 1.5rem;
    margin-bottom: 1.5rem;
}
.dna-title {
    font-size: 0.75rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #818cf8;
    margin-bottom: 1rem;
}

/* Pill badges */
.pill {
    display: inline-block;
    padding: 0.25rem 0.75rem;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 600;
    margin: 0.2rem;
}
.pill-purple { background: #4c1d95; color: #c4b5fd; }
.pill-blue   { background: #1e3a5f; color: #93c5fd; }
.pill-green  { background: #064e3b; color: #6ee7b7; }
.pill-yellow { background: #78350f; color: #fcd34d; }
.pill-red    { background: #7f1d1d; color: #fca5a5; }
.pill-gray   { background: #1f2937; color: #9ca3af; }

/* Color swatch */
.color-swatch {
    display: inline-block;
    width: 18px; height: 18px;
    border-radius: 4px;
    border: 1px solid rgba(255,255,255,0.2);
    vertical-align: middle;
    margin-right: 6px;
}

/* Metric card */
.metric-card {
    background: rgba(30,27,75,0.4);
    border: 1px solid rgba(55,48,163,0.4);
    border-radius: 12px;
    padding: 1rem 1.25rem;
    text-align: center;
}
.metric-value {
    font-size: 1.8rem;
    font-weight: 800;
    color: #a78bfa;
    line-height: 1;
}
.metric-label {
    font-size: 0.75rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-top: 0.3rem;
}

/* Step label */
.step-label {
    font-size: 0.7rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: #6366f1;
    font-weight: 600;
}

/* Section header */
.section-header {
    font-size: 1rem;
    font-weight: 700;
    color: #e2e8f0;
    border-left: 3px solid #6366f1;
    padding-left: 0.75rem;
    margin: 1.5rem 0 0.75rem 0;
}

/* Upload zone */
.upload-hint {
    color: #475569;
    font-size: 0.85rem;
    margin-top: 0.5rem;
}

/* Timeline row */
.tl-row {
    background: rgba(15,15,30,0.5);
    border: 1px solid rgba(55,48,163,0.25);
    border-radius: 8px;
    padding: 0.6rem 0.9rem;
    margin-bottom: 0.4rem;
    font-size: 0.82rem;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
# Helper: color swatch HTML
# ─────────────────────────────────────────────────────────────────────────────

def _swatch(hex_color: str) -> str:
    return f'<span class="color-swatch" style="background:{hex_color};"></span>'


def _pill(text: str, color: str = "purple") -> str:
    return f'<span class="pill pill-{color}">{text}</span>'


def _bool_pill(val: bool, true_label: str, false_label: str) -> str:
    if val:
        return _pill(f"✓ {true_label}", "green")
    return _pill(f"✗ {false_label}", "gray")


# ─────────────────────────────────────────────────────────────────────────────
# Karaoke highlight detection helpers
# ─────────────────────────────────────────────────────────────────────────────

def _is_accent_yellow(hex_color: str) -> bool:
    """Return True if the hex color is in the yellow/amber hue range."""
    import cv2, numpy as np
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except (ValueError, IndexError):
        return False
    pixel = np.array([[[b, g, r]]], dtype=np.uint8)
    hsv   = cv2.cvtColor(pixel, cv2.COLOR_BGR2HSV)[0, 0]
    hue, sat, val = int(hsv[0]), int(hsv[1]), int(hsv[2])
    # Yellow/amber: hue 18–38 (OpenCV 0-180 scale), well-saturated, bright
    return (18 <= hue <= 38) and sat > 80 and val > 140


def _bboxes_overlap(a, b, margin: int = 30) -> bool:
    """Return True if two (x,y,w,h) boxes overlap or are within *margin* px."""
    if a is None or b is None:
        return False
    ax1, ay1, ax2, ay2 = a[0]-margin, a[1]-margin, a[0]+a[2]+margin, a[1]+a[3]+margin
    bx1, by1, bx2, by2 = b[0],        b[1],        b[0]+b[2],        b[1]+b[3]
    return ax1 < bx2 and ax2 > bx1 and ay1 < by2 and ay2 > by1


def _tag_karaoke_highlights(segments, style_results):
    """
    Detect karaoke-style word highlights and tag them in-place.

    A segment is classified as a karaoke highlight when:
      1. Duration ≤ 0.6s
      2. Font colour is yellow/amber (the active-word accent colour)
      3. Its bbox spatially overlaps a longer co-visible parent caption

    Tagged segments get:
        _karaoke_highlight  = True
        _karaoke_highlight_color = hex
        _karaoke_parent_text     = parent caption text
    """
    MAX_DUR = 0.6

    for i, (seg, sr) in enumerate(zip(segments, style_results)):
        if seg.duration() > MAX_DUR:
            continue
        if not _is_accent_yellow(sr.font_color_hex):
            continue

        rb = seg.representative_bbox()
        # Find a longer co-visible parent whose bbox overlaps
        for j, parent in enumerate(segments):
            if i == j or parent.duration() <= MAX_DUR:
                continue
            # Co-visible check
            if seg.start_time >= parent.end_time or seg.end_time <= parent.start_time:
                continue
            prb = parent.representative_bbox()
            if _bboxes_overlap(rb, prb):
                seg._karaoke_highlight       = True
                seg._karaoke_highlight_color = sr.font_color_hex
                seg._karaoke_parent_text     = parent.text
                break

    return segments, style_results


# ─────────────────────────────────────────────────────────────────────────────
# Main pipeline runner — called with a temporary video path
# ─────────────────────────────────────────────────────────────────────────────

def run_pipeline(
    video_path:     str,
    sample_fps:     float,
    min_confidence: float,
    use_gpu:        bool,
) -> dict:
    """Run the full analysis pipeline and return the report dict."""

    # ── Initialise components ────────────────────────────────────────────────
    detector = TextDetector(gpu=use_gpu, min_confidence=min_confidence)
    tracker  = CaptionTracker()
    cutter   = CutDetector()

    # ── Get video metadata ───────────────────────────────────────────────────
    meta = get_video_meta(video_path)
    total_frames_approx = int(meta["duration_sec"] * sample_fps)

    progress  = st.progress(0)
    status_ph = st.empty()

    # Helper to store middle-frame references per segment (for style analysis)
    frame_store: dict[int, np.ndarray] = {}   # sampled_frame_idx -> bgr

    # ── Stage 1 + 2 + 3: extract | detect | track | cut-detect in one pass ──
    status_ph.markdown('<p class="step-label">🎞 Stage 1/5 — Extracting frames & running OCR…</p>',
                       unsafe_allow_html=True)

    for fd in extract_frames(video_path, sample_fps=sample_fps):
        # Store every Nth frame for later style analysis
        frame_store[fd.index] = fd.bgr

        # OCR
        boxes = detector.detect(fd.bgr)

        # Track
        tracker.update(fd.index, fd.timestamp, boxes)

        # Cut / zoom
        cutter.process_frame(fd.index, fd.timestamp, fd.bgr)

        # Progress
        pct = min(0.70, (fd.index + 1) / max(total_frames_approx, 1) * 0.70)
        progress.progress(pct)

    # Flush tracker
    tracker.flush(
        frame_idx = max(frame_store.keys()) if frame_store else 0,
        timestamp = meta["duration_sec"],
    )
    # Pass video dimensions so the corner-position watermark filter works
    segments    = tracker.get_segments(
        video_duration = meta["duration_sec"],
        video_w        = meta["width"],
        video_h        = meta["height"],
    )
    static_text = tracker.get_static_text()   # watermarks / title cards filtered out

    status_ph.markdown('<p class="step-label">🎨 Stage 2/5 — Analysing caption styles…</p>',
                       unsafe_allow_html=True)
    progress.progress(0.75)

    # ── Stage 4: Style analysis ──────────────────────────────────────────────
    style_results = []
    for seg in segments:
        # Use the middle frame of the segment's appearance
        mid_idx  = (seg.start_frame + seg.end_frame) // 2
        # Find the closest stored frame key
        if frame_store:
            closest = min(frame_store.keys(), key=lambda k: abs(k - mid_idx))
            frame   = frame_store[closest]
        else:
            continue
        sr = StyleAnalyzer.analyze(seg, frame, meta["height"], meta["width"])
        style_results.append(sr)

    # ── Brand-color post-filter ───────────────────────────────────────────────
    # Segments whose font colour is in the orange/amber hue band are almost
    # certainly brand watermarks (CAGEI, THE, IHB …) cycling in/out.
    # Move them to static_text so they don't skew the style DNA.
    clean_segments:      list = []
    clean_style_results: list = []
    for seg, sr in zip(segments, style_results):
        if is_brand_color(sr.font_color_hex):
            seg._static_reason = "brand_color_orange"
            static_text.append(seg)
        else:
            clean_segments.append(seg)
            clean_style_results.append(sr)
    segments      = clean_segments
    style_results = clean_style_results

    # ── Karaoke highlight detection ───────────────────────────────────────────
    # A segment is a karaoke highlight if ALL three hold:
    #   1. Duration ≤ 0.6s  (it's a flash, not a persistent caption)
    #   2. Color is yellow/amber hue (the active-word accent colour)
    #   3. Its bounding box spatially overlaps a longer parent caption that is
    #      visible at the same time
    # Matched highlights are tagged and separated from regular captions so they
    # don't skew the style DNA aggregation.
    segments, style_results = _tag_karaoke_highlights(segments, style_results)

    status_ph.markdown('<p class="step-label">🎞 Stage 3/5 — Detecting animations…</p>',
                       unsafe_allow_html=True)
    progress.progress(0.82)

    # ── Stage 5: Animation analysis ─────────────────────────────────────────
    anim_results = [AnimationAnalyzer.analyze(seg) for seg in segments]

    status_ph.markdown('<p class="step-label">✂️ Stage 4/5 — Finalising cut + zoom data…</p>',
                       unsafe_allow_html=True)
    progress.progress(0.90)

    cut_results = cutter.get_results()

    status_ph.markdown('<p class="step-label">📦 Stage 5/5 — Building report…</p>',
                       unsafe_allow_html=True)
    progress.progress(0.97)

    report = build_report(
        video_meta    = meta,
        style_results = style_results,
        anim_results  = anim_results,
        cut_results   = cut_results,
        segments      = segments,
        sample_fps    = sample_fps,
        static_text   = static_text,
    )

    progress.progress(1.0)
    status_ph.empty()
    return report


# ─────────────────────────────────────────────────────────────────────────────
# Render report UI
# ─────────────────────────────────────────────────────────────────────────────

def render_report(report: dict) -> None:
    dna     = report.get("style_dna", {})
    style   = report.get("caption_style", {})
    anim    = report.get("animation_pattern", {})
    editing = report.get("editing_style", {})
    meta    = report.get("video_meta", {})
    tl      = report.get("caption_timeline", [])

    # ── Headline metrics ─────────────────────────────────────────────────────
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{meta.get('duration_sec', '—')}s</div>
            <div class="metric-label">Duration</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{meta.get('total_captions_found', 0)}</div>
            <div class="metric-label">Captions found</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{editing.get('cut_count', 0)}</div>
            <div class="metric-label">Scene cuts</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        interval = editing.get("avg_cut_interval_sec")
        val_str  = f"{interval}s" if interval else "N/A"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{val_str}</div>
            <div class="metric-label">Avg cut interval</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # ── Style DNA card ───────────────────────────────────────────────────────
    st.markdown('<div class="dna-card">', unsafe_allow_html=True)
    st.markdown('<div class="dna-title">🧬 Style DNA — Viral Template Breakdown</div>',
                unsafe_allow_html=True)

    left, right = st.columns(2)

    with left:
        font_hex = dna.get("font_color", "#FFFFFF")
        stroke_hex = dna.get("stroke_color", "#000000")

        st.markdown(f"""
        **🎨 Caption Styling**

        {_swatch(font_hex)} **Font color:** {font_hex}<br>
        📐 **Font size:** {dna.get('font_size_px', '—')} px — {dna.get('font_size_label', '—')}<br>
        🔡 **Font weight:** {_pill(dna.get('font_weight', 'unknown'), 'blue')}<br>
        🖊 **Font family:** {_pill(dna.get('font_family', 'unknown'), 'purple')}<br>
        📍 **Position:** {_pill(dna.get('caption_position', '—').replace('_', ' '), 'purple')}<br>
        🖌 **Stroke:** {_bool_pill(dna.get('stroke', False), 'Yes — ' + stroke_hex, 'None')} {_swatch(stroke_hex) if dna.get('stroke') else ''}<br>
        🌘 **Shadow:** {_bool_pill(dna.get('shadow', False), 'Yes', 'No')}<br>
        🪟 **BG style:** {_pill(dna.get('background', 'none'), 'gray')}
        """, unsafe_allow_html=True)

    with right:
        st.markdown(f"""
        **🎞 Animation & Editing**

        ▶ **Entry anim:** {_pill(dna.get('entry_animation', 'static').replace('_', ' '), 'green')}<br>
        ◀ **Exit anim:** {_pill(dna.get('exit_animation', 'static').replace('_', ' '), 'yellow')}<br>
        📝 **Word-by-word:** {_bool_pill(dna.get('word_by_word', False), 'Yes', 'No')}<br>
        ✂️ **Cut speed:** {_pill(dna.get('editing_pace', '—'), 'red')} — {dna.get('cut_frequency', 'N/A')}<br>
        🔍 **Zoom events:** {_pill(str(dna.get('zoom_events', 0)), 'blue')}<br>
        🎵 **Karaoke style:** {_bool_pill(dna.get('karaoke_style', False), f"Yes — {dna.get('karaoke_highlight_color','')}", 'No')} {_swatch(dna.get('karaoke_highlight_color','#000000')) if dna.get('karaoke_style') else ''}
        """, unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)  # close dna-card

    # ── Per-section detail ───────────────────────────────────────────────────
    with st.expander("📊 Detailed Caption Style Breakdown", expanded=False):
        cs1, cs2 = st.columns(2)
        with cs1:
            st.json({
                "dominant_font_color": style.get("dominant_font_color"),
                "avg_font_size_px":    style.get("avg_font_size_px"),
                "font_weight":         style.get("font_weight"),
                "position_pattern":    style.get("position_pattern"),
            })
        with cs2:
            st.json({
                "has_stroke":       style.get("has_stroke"),
                "stroke_color":     style.get("stroke_color"),
                "has_shadow":       style.get("has_shadow"),
                "background_style": style.get("background_style"),
            })

    # ── Karaoke highlights expander ──────────────────────────────────────────
    karaoke_items = report.get("karaoke_highlights", [])
    if karaoke_items:
        with st.expander(f"🎵 Karaoke Highlights ({len(karaoke_items)} active-word flashes)", expanded=False):
            st.caption("These are short accent-colored words that flash over a parent caption — the 'active speaking word' highlight pattern.")
            for item in karaoke_items:
                hc = item.get("karaoke_highlight_color", "")
                st.markdown(
                    f'<div class="tl-row" style="border-color:rgba(255,200,0,0.35);">'
                    f'🎵 {_swatch(hc)}<b>{item.get("text","")}</b> '
                    f'&nbsp;·&nbsp; {item.get("start_time",0):.1f}s–{item.get("end_time",0):.1f}s '
                    f'&nbsp;·&nbsp; highlight of: <i>{item.get("karaoke_parent_caption","")[:40]}</i> '
                    f'{_pill(hc, "yellow")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )

    with st.expander("🎞 Animation Pattern Detail", expanded=False):
        st.json(anim)

    with st.expander("✂️ Cut & Zoom Detail", expanded=False):
        st.json({
            "cut_count":            editing.get("cut_count"),
            "avg_cut_interval_sec": editing.get("avg_cut_interval_sec"),
            "cut_timestamps":       editing.get("cut_timestamps", [])[:20],   # cap long lists
            "zoom_event_count":     editing.get("zoom_event_count"),
            "zoom_events":          editing.get("zoom_events", []),
        })

    with st.expander(f"📋 Caption Timeline ({len(tl)} segments)", expanded=False):
        if not tl:
            st.info("No captions detected in this video.")
        else:
            for i, entry in enumerate(tl[:50]):   # show max 50 in UI
                anim_label = entry.get("animation", {}).get("entry_animation", "static")
                style_label = entry.get("style", {}).get("font_color", "")
                st.markdown(
                    f'<div class="tl-row">'
                    f'<b>{i+1}.</b> '
                    f'[{entry.get("start_time", 0):.1f}s → {entry.get("end_time", 0):.1f}s] '
                    f'{_swatch(style_label) if style_label else ""}'
                    f'<b>{entry.get("text", "")[:80]}</b> '
                    f'{_pill(anim_label, "blue")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
            if len(tl) > 50:
                st.caption(f"… and {len(tl) - 50} more in the JSON report.")

    with st.expander("🔍 Raw JSON Report", expanded=False):
        st.json(report)

    # ── Filtered overlays (transparency section) ──────────────────────────────
    static_items = report.get("filtered_static_overlays", [])
    if static_items:
        with st.expander(
            f"🚫 Filtered Static Overlays ({len(static_items)} excluded from analysis)",
            expanded=False,
        ):
            st.caption(
                "These text regions were detected but classified as watermarks, "
                "usernames, title cards, or UI elements — NOT rolling captions. "
                "They are excluded from the style analysis above."
            )
            for item in static_items:
                reason_map = {
                    "duration_ratio":    "⏱ Visible for too long (persistent overlay)",
                    "corner_position":   "📍 Located in a corner (watermark position)",
                    "text_too_short":    "🔤 Text too short (symbol/icon/OCR noise)",
                    "brand_color_orange":"🟠 Orange brand color (logo/watermark)",
                }
                reason_key = item.get("filter_reason", "").split("_")[0] + "_" + item.get("filter_reason", "").split("_")[1] if "_" in item.get("filter_reason", "") else item.get("filter_reason", "")
                reason_label = next(
                    (v for k, v in reason_map.items() if item.get("filter_reason", "").startswith(k)),
                    item.get("filter_reason", "unknown")
                )
                st.markdown(
                    f'<div class="tl-row" style="border-color:rgba(127,29,29,0.4); opacity:0.7;">'
                    f'🚫 <b>{item.get("text", "")[:60]}</b> '
                    f'&nbsp;·&nbsp; {item.get("start_time", 0):.1f}s–{item.get("end_time", 0):.1f}s '
                    f'&nbsp;·&nbsp; {_pill(reason_label, "red")}'
                    f'</div>',
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# Main app layout
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    # Hero header
    st.markdown('<h1 class="hero-title">🎬 AI Video Style Analyzer</h1>', unsafe_allow_html=True)
    st.markdown(
        '<p class="hero-sub">Upload a YouTube Short MP4 → Get the full viral template DNA: '
        'font, color, stroke, animation, cuts, and zoom behavior.</p>',
        unsafe_allow_html=True,
    )

    # ── Sidebar — settings ────────────────────────────────────────────────────
    with st.sidebar:
        st.markdown("### ⚙️ Analysis Settings")
        sample_fps = st.slider(
            "Frame sample rate (FPS)",
            min_value=1, max_value=15, value=5, step=1,
            help="Higher = more accurate but slower. 5 FPS is optimal for most Shorts.",
        )
        min_confidence = st.slider(
            "OCR confidence threshold",
            min_value=0.20, max_value=0.95, value=0.40, step=0.05,
            help="Only keep text detections above this confidence level.",
        )
        use_gpu = st.toggle(
            "Use GPU (CUDA)",
            value=True,
            help="EasyOCR will try to use your NVIDIA GPU. Disable if you see CUDA errors.",
        )
        st.markdown("---")
        st.markdown("""
        **📌 Tips**
        - Best results with CapCut-style Shorts with bold white text
        - 5 FPS = ~300 frames for a 60s Short (~30-60s processing)
        - Turn GPU off if you see CUDA out-of-memory errors
        """)

    # ── File upload ───────────────────────────────────────────────────────────
    col_up, col_info = st.columns([2, 1])
    with col_up:
        st.markdown('<p class="section-header">📁 Upload Video</p>', unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "Upload an MP4 file",
            type=["mp4", "mov", "avi"],
            label_visibility="collapsed",
        )
        st.markdown(
            '<p class="upload-hint">Supported: MP4, MOV, AVI — max size depends on your browser.</p>',
            unsafe_allow_html=True,
        )

    with col_info:
        st.markdown('<p class="section-header">ℹ️ What this detects</p>', unsafe_allow_html=True)
        st.markdown("""
        - 🎨 Font color, size, weight
        - 📍 Caption position pattern
        - 🖌 Stroke & shadow presence
        - 🎞 Entry/exit animation type
        - 📝 Word-by-word detection
        - ✂️ Cut frequency & timing
        - 🔍 Zoom/punch-in events
        """)

    # ── Analyse button ────────────────────────────────────────────────────────
    if uploaded is not None:
        st.markdown("---")
        analyze_btn = st.button(
            "🚀 Analyze Video",
            type="primary",
            use_container_width=True,
        )

        if analyze_btn:
            # Save upload to a temp file (OpenCV needs a path, not a file object)
            suffix = "." + uploaded.name.rsplit(".", 1)[-1]
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(uploaded.read())
                tmp_path = tmp.name

            try:
                st.markdown("---")
                st.markdown('<p class="section-header">⚙️ Running Analysis Pipeline</p>',
                            unsafe_allow_html=True)

                report = run_pipeline(
                    video_path     = tmp_path,
                    sample_fps     = float(sample_fps),
                    min_confidence = min_confidence,
                    use_gpu        = use_gpu,
                )

                # Store in session state so it persists on re-renders
                st.session_state["report"]    = report
                st.session_state["filename"]  = uploaded.name

            except Exception as e:
                st.error(f"❌ Analysis failed: {e}")
                st.code(traceback.format_exc())
            finally:
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass

    # ── Display cached report ─────────────────────────────────────────────────
    if "report" in st.session_state:
        report   = st.session_state["report"]
        filename = st.session_state.get("filename", "video.mp4")

        st.markdown("---")
        st.success(f"✅ Analysis complete for **{filename}**")

        st.markdown('<p class="section-header">📊 Analysis Results</p>', unsafe_allow_html=True)
        render_report(report)

        # ── Download ─────────────────────────────────────────────────────────
        st.markdown("---")
        json_bytes = json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8")
        out_name   = filename.rsplit(".", 1)[0] + "_style_report.json"
        st.download_button(
            label            = "📥 Download Full JSON Report",
            data             = json_bytes,
            file_name        = out_name,
            mime             = "application/json",
            use_container_width = True,
        )

    elif uploaded is None:
        # Empty state
        st.markdown("---")
        st.markdown("""
        <div style="text-align:center; padding:3rem 0; color:#374151;">
            <div style="font-size:4rem;">🎬</div>
            <div style="font-size:1.2rem; font-weight:600; color:#6366f1; margin:0.5rem 0;">
                Upload a Short to get started
            </div>
            <div style="font-size:0.9rem; color:#4b5563;">
                The analyzer will reverse-engineer the visual style of any burned-in caption video.
            </div>
        </div>
        """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
