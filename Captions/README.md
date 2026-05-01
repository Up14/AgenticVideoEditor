# AI Video Style Analyzer

Upload a video, get back a JSON file that tells you exactly how the captions in that video are styled — font, color, stroke, animations, cuts, zoom, and more.

Built for reverse-engineering viral short-form videos (YouTube Shorts, Reels, TikTok).

---

## What it does

You give it an MP4. It scans every frame, finds the burned-in captions, and tells you:

- What font is used
- What color the text is
- Whether there's a stroke or shadow
- Where captions sit on screen
- How they animate in and out
- Whether the video uses karaoke-style word highlighting
- How fast the video is edited (cuts per second)
- Where zoom events happen

---

## How to run it

```bash
cd D:\VIDEDI\Captions
.\venv\Scripts\streamlit run app.py
```

Then open `http://localhost:8501` in your browser. Upload a video, hit Analyze.

Or just double-click `run.bat`.

---

## Settings (sidebar)

| Setting | Default | What it does |
|---|---|---|
| Frame sample rate | 5 FPS | How many frames per second to scan. Higher = more accurate, slower. |
| OCR confidence | 0.40 | Only keep text detections above this score. Lower = more detections, more noise. |
| Use GPU | On | Faster if you have CUDA. Turn off if you see CUDA errors. |

---

## Output structure

Everything comes out as a single JSON file you can download. Here's what each section means:

---

### `video_meta`
Basic info about the video.

```json
"video_meta": {
  "duration_sec": 15.73,
  "native_fps": 30,
  "width": 608,
  "height": 1080,
  "sample_fps_used": 5,
  "total_captions_found": 15
}
```

---

### `style_dna`
The headline summary — one quick card that describes the whole video's caption style.

```json
"style_dna": {
  "font_color": "#F2F2F3",
  "font_size_px": 48,
  "font_size_label": "small",
  "font_weight": "regular",
  "font_family": "Arial Black",
  "stroke": true,
  "stroke_color": "#0C0E12",
  "shadow": true,
  "caption_position": "middle_center",
  "background": "none",
  "entry_animation": "static",
  "exit_animation": "static",
  "word_by_word": false,
  "karaoke_style": true,
  "karaoke_highlight_color": "#F8FAA6",
  "karaoke_word_count": 3,
  "cut_frequency": "every 0.25s",
  "editing_pace": "fast",
  "zoom_events": 4
}
```

`font_size_label` is one of: `small`, `medium`, `large`.  
`editing_pace` is one of: `slow`, `medium`, `fast`.  
`karaoke_style: true` means the video highlights the active speaking word in a different color.

---

### `caption_style`
Same as style_dna but the raw aggregated numbers, not the label version.

```json
"caption_style": {
  "dominant_font_color": "#F2F2F3",
  "avg_font_size_px": 48,
  "font_weight": "regular",
  "font_family": "Arial Black",
  "position_pattern": "middle_center",
  "has_stroke": true,
  "stroke_color": "#0C0E12",
  "has_shadow": true,
  "background_style": "none"
}
```

---

### `animation_pattern`
Overall animation behavior across all captions.

```json
"animation_pattern": {
  "entry_animation": "static",
  "exit_animation": "fade_out",
  "word_by_word": false,
  "caption_count": 15
}
```

`entry_animation` is the most common entry type seen across segments.  
Possible values: `static`, `pop_in`, `fade_in`, `slide_left`, `slide_right`, `slide_up`, `word_by_word`.

---

### `editing_style`
Cut and zoom behavior.

```json
"editing_style": {
  "cut_count": 135,
  "avg_cut_interval_sec": 0.25,
  "cut_timestamps": [4.0, 5.2, 5.6, ...],
  "zoom_event_count": 4,
  "zoom_events": [
    {
      "start": 3.0,
      "end": 3.8,
      "type": "zoom_in",
      "avg_magnitude": 3.122
    }
  ]
}
```

---

### `caption_timeline`
Every detected caption, one entry per segment, in order.

```json
"caption_timeline": [
  {
    "text": "bhagwan mere",
    "start_time": 1.6,
    "end_time": 6.0,
    "duration": 4.4,
    "bbox": { "x": 163, "y": 561, "w": 260, "h": 57 },
    "karaoke_highlight": false,
    "style": {
      "font_color": "#EEEEEF",
      "font_size_px": 57,
      "font_weight": "regular",
      "font_family": "Arial Black",
      "font_family_confidence": 0.606,
      "font_family_top3": [
        { "font": "Arial Black", "score": 0.606 },
        { "font": "AlfaSlabOne-Regular", "score": 0.217 },
        { "font": "Bangers-Regular", "score": 0.036 }
      ],
      "position": "middle_center",
      "position_norm": { "x": 0.482, "y": 0.545 },
      "has_stroke": true,
      "stroke_color": "#111316",
      "has_shadow": false,
      "background_style": "none"
    },
    "animation": {
      "entry_animation": "word_by_word",
      "exit_animation": "slide_out",
      "word_by_word": true,
      "entry_frames": 18
    }
  }
]
```

`position_norm` is x/y as a 0–1 fraction of the frame width/height.  
`font_family_confidence` is how confident the model is. Above 0.35 = reliable. Below 0.25 = treat as a guess.

---

### `karaoke_highlights`
Only present if karaoke-style highlighting was detected. Lists every flash word separately.

```json
"karaoke_highlights": [
  {
    "text": "the",
    "start_time": 0.8,
    "end_time": 1.0,
    "karaoke_highlight": true,
    "karaoke_highlight_color": "#F8FAA6",
    "karaoke_parent_caption": "guy in the"
  }
]
```

These are the yellow (or other accent color) words that flash briefly over a base caption as the speaker says that word.

---

### `filtered_static_overlays`
Text that was detected but filtered out because it's not a caption — watermarks, logo overlays, usernames, etc.

```json
"filtered_static_overlays": [
  {
    "text": "BHAGWAN MERE KHARCHE BADHAO",
    "start_time": 0,
    "end_time": 15.6,
    "filter_reason": "duration_ratio_0.99"
  },
  {
    "text": "CAGEI",
    "start_time": 0,
    "end_time": 0.8,
    "filter_reason": "brand_color_orange"
  }
]
```

`filter_reason` tells you why it was excluded:
- `duration_ratio_X.XX` — visible for too long, clearly a watermark
- `brand_color_orange` — orange/amber colored text, detected as a brand logo
- `text_too_short` — single character or symbol, not a real caption
- `corner_position` — sitting in a corner, typical watermark placement

---

## What it can and can't detect

**Works well:**
- Font color, size, stroke, shadow
- Caption position on screen
- Entry/exit animations (pop, fade, slide, word-by-word)
- Karaoke word highlights
- Cut count and zoom events
- Brand overlay filtering

**Known limitations:**
- Font family is a guess from a pretrained model — confidence below 0.25 is unreliable
- Captions shorter than ~0.4s may be missed at 5 FPS (increase sample rate to catch them)
- OCR struggles with non-English text, old-style typography, or very small fonts
- Italic detection is not yet separate — italic fonts sometimes get misidentified as Courier/monospace

---

## Files

| File | What it does |
|---|---|
| `app.py` | Streamlit UI and pipeline orchestration |
| `frame_extractor.py` | Pulls frames from the video at the set FPS |
| `text_detector.py` | Runs EasyOCR and merges word boxes into line boxes |
| `caption_tracker.py` | Tracks text across frames, builds segments, filters static overlays |
| `style_analyzer.py` | Reads pixel data from each caption patch — color, stroke, shadow, font |
| `font_recognizer.py` | Font family classification using a ResNet18 model from HuggingFace |
| `animation_analyzer.py` | Detects entry/exit animations from how bboxes change frame-to-frame |
| `cut_detector.py` | Detects scene cuts and zoom events |
| `output_builder.py` | Merges all results into the final JSON |