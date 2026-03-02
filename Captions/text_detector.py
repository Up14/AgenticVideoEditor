"""
text_detector.py
────────────────
Wraps EasyOCR to detect burned-in text regions inside video frames.

Public API
----------
TextDetector(gpu, min_confidence)
    .detect(frame_bgr)  -> list[TextBox]
"""

from __future__ import annotations
import numpy as np
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class TextBox:
    text:       str
    confidence: float
    # four-corner polygon returned by EasyOCR [[TL],[TR],[BR],[BL]]
    polygon:    list
    # derived convenience values
    cx: int = 0        # center x (pixels)
    cy: int = 0        # center y (pixels)
    x: int  = 0        # left edge
    y: int  = 0        # top edge
    w: int  = 0        # width
    h: int  = 0        # height

    def __post_init__(self):
        xs = [p[0] for p in self.polygon]
        ys = [p[1] for p in self.polygon]
        self.x  = int(min(xs))
        self.y  = int(min(ys))
        self.w  = int(max(xs) - min(xs))
        self.h  = int(max(ys) - min(ys))
        self.cx = self.x + self.w // 2
        self.cy = self.y + self.h // 2

    def area(self) -> int:
        return self.w * self.h

    def to_dict(self) -> dict:
        return {
            "text":       self.text,
            "confidence": round(self.confidence, 3),
            "x": self.x, "y": self.y,
            "w": self.w, "h": self.h,
            "cx": self.cx, "cy": self.cy,
        }



def _merge_line_boxes(boxes: list, line_gap_px: int = 18, word_gap_px: int = 60) -> list:
    """
    Merge individual word-level TextBoxes into line-level TextBoxes.

    Two boxes are merged into the same line if:
      - Their vertical centres are within *line_gap_px* pixels of each other
      - They are horizontally within *word_gap_px* pixels of each other

    Within each line, boxes are sorted left→right and their text is joined
    with a space.  The merged bounding box is the union of all component boxes.
    """
    if not boxes:
        return boxes

    # Sort top→bottom, then left→right
    sorted_boxes = sorted(boxes, key=lambda b: (b.cy, b.cx))

    lines: list[list] = []  # list of groups

    for box in sorted_boxes:
        merged = False
        for line in lines:
            # Compare against the last box in the line
            ref = line[-1]
            same_row  = abs(box.cy - ref.cy) <= line_gap_px
            close_h   = box.x <= ref.x + ref.w + word_gap_px
            if same_row and close_h:
                line.append(box)
                merged = True
                break
        if not merged:
            lines.append([box])

    # Build merged TextBox objects for each line
    result = []
    for line in lines:
        if len(line) == 1:
            result.append(line[0])
            continue

        # Sort within line left→right
        line.sort(key=lambda b: b.cx)

        # Union bounding box
        x1 = min(b.x for b in line)
        y1 = min(b.y for b in line)
        x2 = max(b.x + b.w for b in line)
        y2 = max(b.y + b.h for b in line)

        merged_text = " ".join(b.text for b in line)
        avg_conf    = sum(b.confidence for b in line) / len(line)

        # Build a simple polygon (top-left, top-right, bottom-right, bottom-left)
        polygon = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
        result.append(TextBox(text=merged_text, confidence=avg_conf, polygon=polygon))

    return result


class TextDetector:

    """
    Lazy-loads EasyOCR on first `.detect()` call so Streamlit can import
    the module without immediately loading the model.
    """

    def __init__(self, gpu: bool = True, min_confidence: float = 0.4):
        self._gpu            = gpu
        self._min_confidence = min_confidence
        self._reader: Optional[object] = None

    def _load_reader(self):
        if self._reader is None:
            import easyocr
            self._reader = easyocr.Reader(
                lang_list   = ["en"],
                gpu         = self._gpu,
                verbose     = False,
            )

    def detect(self, frame_bgr: np.ndarray) -> list[TextBox]:
        """
        Run EasyOCR on *frame_bgr* and return detected text boxes above
        the confidence threshold.
        """
        self._load_reader()

        # EasyOCR works best with RGB
        frame_rgb = frame_bgr[:, :, ::-1]

        try:
            results = self._reader.readtext(frame_rgb, detail=1)
        except Exception:
            return []

        boxes = []
        for (polygon, text, conf) in results:
            text = text.strip()
            if not text:
                continue
            if conf < self._min_confidence:
                continue
            boxes.append(TextBox(text=text, confidence=conf, polygon=polygon))

        # Merge individual word boxes on the same line into single TextBoxes
        return _merge_line_boxes(boxes)
