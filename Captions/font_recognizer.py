"""
font_recognizer.py
──────────────────
Font family recognition using gaborcselle/font-identifier:
a ResNet18 visual classifier that identifies 48 standard fonts
from image patches with ~96% accuracy.

Public API
----------
FontRecognizer()
    .recognize(patch_bgr)   -> dict  {"font_family", "confidence", "top3"}
    .aggregate(font_list)   -> str   (majority-vote font name)
"""

from __future__ import annotations
import numpy as np
import cv2
from typing import Optional


# ──────────────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────────────

MODEL_NAME  = "gaborcselle/font-identifier"
INPUT_SIZE  = 224        # ResNet18 input size
MIN_PATCH_W = 20         # patches smaller than this → unknown
MIN_PATCH_H = 10


# ──────────────────────────────────────────────────────────────────────────────
# FontRecognizer
# ──────────────────────────────────────────────────────────────────────────────

class FontRecognizer:
    """
    Lazy-loads the HuggingFace font-identifier model on first `.recognize()`
    call so the module can be imported without triggering a model download.
    """

    def __init__(self):
        self._pipe = None   # transformers ImageClassificationPipeline

    # ── private ──────────────────────────────────────────────────────────────

    def _load(self):
        if self._pipe is not None:
            return
        try:
            from transformers import pipeline
            self._pipe = pipeline(
                "image-classification",
                model  = MODEL_NAME,
                top_k  = 5,
            )
        except Exception as e:
            self._pipe = None
            raise RuntimeError(f"FontRecognizer: failed to load model — {e}")

    @staticmethod
    def _preprocess(patch_bgr: np.ndarray) -> "PIL.Image":
        """Convert a BGR numpy patch to a PIL RGB image sized for ResNet18."""
        from PIL import Image
        # Upscale tiny patches so the model has enough detail
        h, w = patch_bgr.shape[:2]
        scale = max(INPUT_SIZE / w, INPUT_SIZE / h, 1.0)
        if scale > 1.0:
            new_w = max(int(w * scale), INPUT_SIZE)
            new_h = max(int(h * scale), INPUT_SIZE)
            patch_bgr = cv2.resize(patch_bgr, (new_w, new_h),
                                   interpolation=cv2.INTER_CUBIC)
        # Centre-crop to INPUT_SIZE × INPUT_SIZE
        h2, w2 = patch_bgr.shape[:2]
        y_start = max((h2 - INPUT_SIZE) // 2, 0)
        x_start = max((w2 - INPUT_SIZE) // 2, 0)
        cropped = patch_bgr[y_start:y_start + INPUT_SIZE,
                            x_start:x_start + INPUT_SIZE]
        rgb = cv2.cvtColor(cropped, cv2.COLOR_BGR2RGB)
        return Image.fromarray(rgb)

    # ── public ───────────────────────────────────────────────────────────────

    def recognize(self, patch_bgr: np.ndarray) -> dict:
        """
        Predict the font family for a BGR image patch.

        Returns
        -------
        {
            "font_family":  str,    # top-1 prediction
            "confidence":   float,  # 0.0–1.0
            "top3": [               # top-3 candidates
                {"font": str, "score": float},
                ...
            ]
        }
        """
        _unknown = {
            "font_family": "unknown",
            "confidence":  0.0,
            "top3": [],
        }

        if patch_bgr is None or patch_bgr.size == 0:
            return _unknown

        h, w = patch_bgr.shape[:2]
        if w < MIN_PATCH_W or h < MIN_PATCH_H:
            return _unknown

        try:
            self._load()
            pil_img = self._preprocess(patch_bgr)
            results = self._pipe(pil_img)   # list of {label, score}
        except Exception:
            return _unknown

        if not results:
            return _unknown

        top1  = results[0]
        top3  = [{"font": r["label"], "score": round(r["score"], 3)}
                 for r in results[:3]]

        return {
            "font_family": top1["label"],
            "confidence":  round(top1["score"], 3),
            "top3":        top3,
        }

    @staticmethod
    def aggregate(font_families: list[str]) -> str:
        """
        Return the majority-vote font family from a list of per-segment
        predictions.  'unknown' entries are excluded from the vote.
        """
        votes = [f for f in font_families if f and f != "unknown"]
        if not votes:
            return "unknown"
        counts: dict[str, int] = {}
        for f in votes:
            counts[f] = counts.get(f, 0) + 1
        return max(counts, key=counts.get)
