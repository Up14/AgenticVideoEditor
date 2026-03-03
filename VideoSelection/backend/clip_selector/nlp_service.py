"""
NLP Service — sentence feature detection, sentence reconstruction, and transcript parsing.

Verbatim port of NLP logic from ExistingCode/ClipSelector/app.py.
All Streamlit calls replaced with logging + exceptions.
spaCy model loaded once as a module-level singleton.
"""

import os
import re
import logging
from datetime import timedelta

import spacy

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# spaCy model — loaded once on import (replaces @st.cache_resource)
# ---------------------------------------------------------------------------
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("en_core_web_sm")
            logger.info("spaCy model 'en_core_web_sm' loaded.")
        except OSError:
            logger.info("Downloading spaCy model 'en_core_web_sm'...")
            os.system("python -m spacy download en_core_web_sm")
            _nlp = spacy.load("en_core_web_sm")
    return _nlp


# ---------------------------------------------------------------------------
# SentenceFeatureDetector (lines 101-205 of app.py — unchanged)
# ---------------------------------------------------------------------------
class SentenceFeatureDetector:
    """Detects discourse and viral signals in sentences using spaCy."""

    # Use regex with word boundaries for precision
    RESOLUTION_MARKERS = re.compile(
        r'\b(therefore|conclusion|which means|that is why|this is why|so i think|the point is|this is what)\b',
        re.I
    )

    CONTRAST_MARKERS = {"but", "however", "yet", "instead", "whereas"}

    FRAMING_MARKERS = {
        "the problem is", "nobody talks about", "here is the thing",
        "most people think", "the reality is", "imagine if"
    }

    ACK_STARTERS = {
        "yes", "no", "yeah", "true", "exactly", "correct",
        "absolutely", "sure", "of course", "only"
    }

    DEPENDENT_STARTERS = {
        "to", "with", "then", "and then", "because", "while", "although",
        "if", "when", "after", "before", "since", "but then", "um", "so", "but"
    }

    DISCOURSE_MARKERS = {
        "right", "well", "look", "listen", "i mean",
        "you know", "true", "yeah", "okay", "ok",
        "no", "uh", "like", "um"
    }

    @staticmethod
    def analyze(sent_text, doc):
        # Pre-Clean Bracket Artifacts (e.g., [snorts] But...)
        text = re.sub(r'^\[[^\]]+\]\s*', '', sent_text).lower().strip()
        features = {
            "is_question": text.endswith("?") or any(token.tag_ == "WP" for token in doc),
            "is_continuation": text.startswith(("and ", "but ", "so ", "because ")),
            "is_referential": text.startswith(("this ", "that ", "it ", "they ", "these ", "those ")),
            "is_resolution": bool(SentenceFeatureDetector.RESOLUTION_MARKERS.search(text)),
            "is_contrast": any(m in text for m in SentenceFeatureDetector.CONTRAST_MARKERS),
            "is_strong_framing": any(m in text for m in SentenceFeatureDetector.FRAMING_MARKERS),
            "has_superlative": any(token.tag_ == "JJS" or token.tag_ == "RBS" for token in doc),
            "has_number": bool(re.search(r'\d+|million|billion|trillion', text)),
            "has_named_entity": len(doc.ents) > 0,
            "word_count": len(doc),
            "topics": {ent.text.lower() for ent in doc.ents} | {chunk.root.text.lower() for chunk in doc.noun_chunks},
            "info_density": sum(1 for t in doc if not t.is_stop) / len(doc) if len(doc) > 0 else 0
        }

        # 1. Discourse Marker Detection
        features["is_discourse_marker"] = any(
            text.startswith(marker + " ") or text == marker
            for marker in SentenceFeatureDetector.DISCOURSE_MARKERS
        )

        # 2. Acknowledgment Detection
        features["is_acknowledgment"] = any(
            text.startswith(marker + " ") or text == marker
            for marker in SentenceFeatureDetector.ACK_STARTERS
        )

        # 3. Compound Continuation Detection (No, but..., Yeah, but...)
        if re.match(r'^(no,\s*|no\s+|yeah,\s*|yeah\s+|well,\s*|well\s+)?but\s+', text):
            features["is_continuation"] = True

        # 4. Refined "So" Handling (Marker vs Resolution)
        if text.startswith("so "):
            # Only resolution if it's a strong summary phrase or very short declarative without conjunctions
            if ("this is why" in text or "that is why" in text or "the point is" in text):
                features["is_resolution"] = True
            elif features["word_count"] < 12 and not any(c in text for c in [",", " and ", " but ", " because "]):
                features["is_resolution"] = True
            else:
                features["is_discourse_marker"] = True

        # 5. Short Dependent Question ("Why?", "How?", "Really?")
        features["is_short_question"] = (
            features["is_question"] and
            features["word_count"] <= 3 and
            not features["has_named_entity"]
        )

        # 6. Dependent Clause Start Detection (Transcription Fragments)
        features["is_dependent_clause_start"] = any(
            text.startswith(word + " ") for word in SentenceFeatureDetector.DEPENDENT_STARTERS
        )

        # Dialogue Pivot (Short, low-density filler: "True.", "Yeah.")
        features["is_pivot"] = features["word_count"] < 5 and features["info_density"] < 0.4

        # Context Dependency Score (0 to 1) - Gradated
        dep_score = 0
        if features["is_referential"]:
            dep_score += 0.4
            if not features["has_named_entity"]:
                dep_score += 0.4  # Strong penalty only for referential + no context

        if features["is_continuation"]:
            dep_score += 0.2
        features["context_dependency_score"] = min(1.0, dep_score)

        # Hook Strength (0 to 1)
        hook_score = 0
        if features["is_question"]:       hook_score += 0.4
        if features["is_contrast"]:       hook_score += 0.3
        if features["is_strong_framing"]: hook_score += 0.3
        if features["has_number"]:        hook_score += 0.1
        features["hook_score"] = min(1.0, hook_score)

        return features


# ---------------------------------------------------------------------------
# reconstruct_sentences (lines 207-260 of app.py — unchanged)
# ---------------------------------------------------------------------------
def reconstruct_sentences(captions):
    """Merges raw captions into semantic sentences with high timestamp precision."""
    if not captions:
        return []

    nlp = _get_nlp()
    sentences = []
    current_doc_text = ""
    caption_map = []  # To track character offsets back to captions

    # Process captions incrementally to avoid offset drift
    for cap in captions:
        start_char = len(current_doc_text)
        current_doc_text += cap['text'] + " "
        end_char = len(current_doc_text)
        caption_map.append({
            "start_char": start_char,
            "end_char": end_char,
            "start_time": cap['start'],
            "end_time": cap['end']
        })

    doc = nlp(current_doc_text)

    for sent in doc.sents:
        raw_text = sent.text.strip()
        if not raw_text:
            continue

        # Level-0 Cleaning: Strip Bracket Artifacts ([snorts], [laughter])
        clean_text = re.sub(r'^\[[^\]]+\]\s*', '', raw_text).strip()
        if not clean_text:
            continue

        s_char = sent.start_char
        e_char = sent.end_char

        # Find precise start/end via mapping
        start_time = caption_map[0]['start_time']
        end_time = caption_map[-1]['end_time']

        # Precise mapping
        for entry in caption_map:
            if s_char >= entry['start_char'] and s_char < entry['end_char']:
                start_time = entry['start_time']
            if e_char > entry['start_char'] and e_char <= entry['end_char']:
                end_time = entry['end_time']
                break

        sentences.append({
            "text": clean_text,
            "start": start_time,
            "end": end_time,
            "features": SentenceFeatureDetector.analyze(clean_text, sent.as_doc())
        })

    return sentences


# ---------------------------------------------------------------------------
# trim_marker (lines 638-652 of app.py — unchanged)
# ---------------------------------------------------------------------------
def trim_marker(text):
    """Strips leading discourse markers/rhetorical tags from clip starts."""
    text_clean = text.strip()

    # Hard Trim for "and " (Structural continuation)
    if text_clean.lower().startswith("and "):
        text_clean = text_clean[4:].lstrip(", ").strip()

    for marker in SentenceFeatureDetector.DISCOURSE_MARKERS:
        if text_clean.lower().startswith(marker + " "):
            text_clean = text_clean[len(marker):].lstrip(", ").strip()
            break
        elif text_clean.lower() == marker:
            return ""  # Skip if only marker remains
    return text_clean


# ---------------------------------------------------------------------------
# parse_and_process_transcript (lines 693-712 of app.py)
# st.error / st.stop replaced with ValueError
# ---------------------------------------------------------------------------
def _time_string_to_seconds(ts):
    parts = ts.split('.')
    h, m, s = map(int, parts[0].split(':'))
    ms = int(parts[1]) if len(parts) > 1 else 0
    return timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms).total_seconds()


def parse_and_process_transcript(data):
    if 'captions' not in data:
        raise ValueError(
            "The captions data does not contain a 'captions' list. "
            "Please check the file format."
        )
    raw_captions = data['captions']
    if not raw_captions:
        return []

    timed_captions = [
        {
            "start": _time_string_to_seconds(c['start']) if isinstance(c['start'], str) else c['start'],
            "end":   _time_string_to_seconds(c['end'])   if isinstance(c['end'],   str) else c['end'],
            "text":  c['text'].strip()
        }
        for c in raw_captions
    ]

    merged = []
    if not timed_captions:
        return []
    current_cap = timed_captions[0].copy()
    for next_cap in timed_captions[1:]:
        if next_cap['text'] == current_cap['text'] or next_cap['text'].startswith(current_cap['text']):
            current_cap['end'] = next_cap['end']
            if len(next_cap['text']) > len(current_cap['text']):
                current_cap['text'] = next_cap['text']
        else:
            merged.append(current_cap)
            current_cap = next_cap.copy()
    merged.append(current_cap)
    return merged
