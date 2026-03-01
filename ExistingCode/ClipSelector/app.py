import streamlit as st
import json
import os
from cerebras.cloud.sdk import Cerebras
from datetime import timedelta
import time
from itertools import cycle
import pandas as pd
import re
import traceback
import spacy
import numpy as np
import io
import zipfile
from sklearn.metrics.pairwise import cosine_similarity

# Load spaCy model
try:
    nlp = spacy.load("en_core_web_sm")
except:
    os.system("python -m spacy download en_core_web_sm")
    nlp = spacy.load("en_core_web_sm")


# ---------------------------------------------------------------------------
# Model storage — all heavy models live on D drive, never on C
# ---------------------------------------------------------------------------
MODELS_DIR = r"D:\models"
SEMANTIC_BOUNDARY_THRESHOLD = 0.65  # cosine sim drop below this → shown as boundary in viz
HARD_STOP_THRESHOLD = 0.25          # catastrophic topic rupture only — story→example or metaphor→punchline are NOT ruptures
os.makedirs(MODELS_DIR, exist_ok=True)


@st.cache_resource(show_spinner="⚙️ Loading Semantic Model (first run: ~90 MB → D:\\models)…")
def get_semantic_model():
    """Loads all-MiniLM-L6-v2.  Downloads to D:\\models on first run, uses cache after."""
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2", cache_folder=MODELS_DIR)


@st.cache_resource(show_spinner="⚙️ Loading Emotion Model (first run: ~500 MB → D:\\models)…")
def get_emotion_model():
    """Loads Cardiff NLP sentiment model to D:\\models.
    Uses AutoTokenizer + AutoModelForSequenceClassification so cache_dir
    only applies at load-time and never leaks into tokenizer inference calls.
    """
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        pipeline as hf_pipeline,
    )
    _name = "cardiffnlp/twitter-roberta-base-sentiment"
    _tok = AutoTokenizer.from_pretrained(_name, cache_dir=MODELS_DIR)
    _mdl = AutoModelForSequenceClassification.from_pretrained(_name, cache_dir=MODELS_DIR)
    return hf_pipeline("sentiment-analysis", model=_mdl, tokenizer=_tok)



# --- Initial Setup ---
st.set_page_config(page_title="Viral Clip Finder", layout="wide")

# --- API Key Management ---
API_KEYS = [
    "csk-5jxf6ktn9jx2w5x3m2cd8h3me5rtpjy5j6d5tj2thjmn9nfv",
    "csk-6wy3mdk8wpme5xj58x95xy5yp32c9r3vrjmfyep8k2wv8whx",
    "csk-wxhj6w3pjjwxm3cmyxjpjrt368r8cenp42y8dehdhvwj394v",
]

class APIKeyManager:
    """Manages API keys, client rotation, and rate limiting."""
    def __init__(self, api_keys, rate_limit=28, period_seconds=60):
        if not api_keys:
            st.error("No API keys provided.")
            st.stop()
        self.clients = {key: Cerebras(api_key=key) for key in api_keys}
        self.key_cycler = cycle(api_keys)
        self.usage = {key: [] for key in api_keys}
        self.rate_limit = rate_limit
        self.period = period_seconds
        self.key_count = len(api_keys)

    def get_client(self):
        checked_keys = 0
        while checked_keys < self.key_count:
            current_key = next(self.key_cycler)
            now = time.monotonic()
            self.usage[current_key] = [ts for ts in self.usage[current_key] if now - ts < self.period]
            if len(self.usage[current_key]) < self.rate_limit:
                self.usage[current_key].append(now)
                return self.clients[current_key]
            checked_keys += 1
        st.warning("All API keys are rate-limited. Pausing...")
        oldest_ts = min(min(ts) for ts in self.usage.values() if ts)
        sleep_time = self.period - (time.monotonic() - oldest_ts) + 1.5
        with st.spinner(f"Waiting for {int(sleep_time)}s for API keys to refresh..."):
            time.sleep(sleep_time)
        return self.get_client()

# --- NLP Production Engine ---

class SentenceFeatureDetector:
    """Detects discourse and viral signals in sentences using spaCy."""
    
    # Use regex with word boundaries for precision
    RESOLUTION_MARKERS = re.compile(r'\b(therefore|conclusion|which means|that is why|this is why|so i think|the point is|this is what)\b', re.I)
    
    CONTRAST_MARKERS = {"but", "however", "yet", "instead", "whereas"}
    
    FRAMING_MARKERS = {
        "the problem is", "nobody talks about", "here is the thing", 
        "most people think", "the reality is", "imagine if"
    }

    ACK_STARTERS = {"yes", "no", "yeah", "true", "exactly", "correct", "absolutely", "sure", "of course", "only"}

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
                dep_score += 0.4 # Strong penalty only for referential + no context
        
        if features["is_continuation"]: dep_score += 0.2
        features["context_dependency_score"] = min(1.0, dep_score)
        
        # Hook Strength (0 to 1)
        hook_score = 0
        if features["is_question"]: hook_score += 0.4
        if features["is_contrast"]: hook_score += 0.3
        if features["is_strong_framing"]: hook_score += 0.3
        if features["has_number"]: hook_score += 0.1
        features["hook_score"] = min(1.0, hook_score)
        
        return features

def reconstruct_sentences(captions):
    """Merges raw captions into semantic sentences with high timestamp precision."""
    if not captions: return []
    
    sentences = []
    current_doc_text = ""
    current_cap_start = captions[0]['start']
    caption_map = [] # To track character offsets back to captions
    
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
        if not raw_text: continue
        
        # Level-0 Cleaning: Strip Bracket Artifacts ([snorts], [laughter])
        clean_text = re.sub(r'^\[[^\]]+\]\s*', '', raw_text).strip()
        if not clean_text: continue
        
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

class CandidateGenerator:
    """Generates candidate clips using index-based O(n) sliding window and discourse pairing."""
    
    @staticmethod
    def _resolve_dependency_start(sentences, i):
        """Hierarchical start logic: Handles backtracking to anchors or skipping weak starts."""
        f = sentences[i]['features']
        
        # 1. Pivot Skip (Absolute filler)
        if f['is_pivot']:
            return None
            
        # 2. Dependency Check (Acknowledgment, Questions, Continuations, Referentials, Clause Fragments)
        is_dep_start = (
            f['is_acknowledgment'] or 
            f['is_short_question'] or 
            f['is_continuation'] or 
            f['is_dependent_clause_start'] or
            (f['is_referential'] and not f['has_named_entity'])
        )
        
        if not is_dep_start:
            # Independent start (but check context dependency)
            if f['context_dependency_score'] > 0.8:
                return None
            return i
            
        # 3. Backtrack Logic for Dependent Starts
        if i == 0:
            return None # Can't backtrack at start of text
            
        # Hard Reject for "But..." starts (unless it's an acknowledgment "no, but")
        text_lower = sentences[i]['text'].lower().strip()
        if text_lower.startswith("but "):
            return None

        prev = sentences[i-1]
        pf = prev['features']
        
        # Stricter Strong Anchor Rule
        is_strong_anchor = (
            (pf['is_question'] and pf['word_count'] > 4) or 
            pf['hook_score'] > 0.6 or 
            pf['has_named_entity'] or 
            pf['is_strong_framing'] or 
            pf['is_resolution']
        )
        
        if is_strong_anchor and not pf['is_pivot']:
            return i - 1 # Backtrack ONE step
            
        return None # Skip weak dependency start

    @staticmethod
    def generate(sentences, min_dur=30, max_dur=65, boundary_indices=None):
        candidates = []
        if not sentences: return candidates
        num_sents = len(sentences)
        
        # 1. Index-Based Sliding Window (O(n) Efficiency)
        for i in range(num_sents):
            f = sentences[i]['features']
            start_idx = CandidateGenerator._resolve_dependency_start(sentences, i)
            if start_idx is None:
                continue
            
            # Additional safety: ensure we don't start on a pivot even after backtrack
            if sentences[start_idx]['features']['is_pivot']:
                continue
                
            best_end = -1
            best_score = -1

            # --- Arc tracking state ---
            has_resolution    = False
            peak_emotion      = 0.0
            boundary_crossed  = False  # crossed at least one hard boundary mid-arc

            for j in range(start_idx, num_sents):
                nxt = sentences[j]
                dur = nxt['end'] - sentences[start_idx]['start']
                if dur > max_dur: break

                nxt_emo = nxt['features'].get('emotion_intensity', 0.0)
                peak_emotion = max(peak_emotion, nxt_emo)

                # Track resolution anywhere in the arc (not just at end)
                if nxt['features']['is_resolution']:
                    has_resolution = True

                # ── Hard semantic rupture (sim < 0.25 = catastrophic, e.g. completely new topic) ──
                if boundary_indices and j in boundary_indices:
                    if dur < min_dur:
                        boundary_crossed = True  # still building — cross it, note the cost
                    else:
                        if has_resolution:
                            # Arc already complete — accept what we have and stop
                            break
                        else:
                            boundary_crossed = True  # mark cost, keep expanding to find closure

                # ── Pivot Reset (structural pivots are hard breaks) ──
                if dur >= min_dur and nxt['features']['is_pivot']:
                    break

                # ── Emotional decay stop (peak was high, now it dropped) ──
                if dur >= min_dur + 8 and peak_emotion > 0.65 and nxt_emo < 0.25:
                    break

                if dur >= min_dur:
                    # ── Best-End Selection (arc completeness score) ──
                    score = 0
                    if has_resolution:                             score = 3
                    elif nxt['text'].endswith(('.', '?', '!')):   score = 1

                    # Boundary crossing is a cost: demote score by 1 tier
                    if boundary_crossed and score > 0:
                        score = max(0, score - 1)

                    # Forward Expansion: questions inside arc are fine — keep looking for resolution
                    if score <= 1 and dur < max_dur - 10:
                        clip_so_far = sentences[start_idx:j+1]
                        q_count_so_far = sum(1 for s in clip_so_far if s['features']['is_question'])
                        if q_count_so_far >= 2:  # lower bar: even 2 Qs means answer likely coming
                            ans_words = 0
                            for k in range(j, start_idx-1, -1):
                                if sentences[k]['features']['is_question']: break
                                ans_words += sentences[k]['features']['word_count']
                            if ans_words < 15: score = 0  # Force lookahead until answer is substantial

                    if score > best_score or (score == best_score and j >= best_end):
                        best_score = score
                        best_end = j

                    # Only early-exit on a strong resolution that has time to breathe
                    if has_resolution and best_score == 3 and dur > min_dur + 15:
                        break
            
            if best_end != -1:
                clip_sents = sentences[start_idx:best_end+1]
                
                # Step 3: Final Content Repair (Cleaning rhetorical starts)
                clip_text_parts = [s['text'] for s in clip_sents]
                # Universal Start Trimming: Fixes structural leakage even after backtrack
                first_f = clip_sents[0]['features']
                if first_f['is_discourse_marker'] or first_f['is_continuation'] or first_f['is_acknowledgment']:
                    clip_text_parts[0] = trim_marker(clip_text_parts[0])
                
                # Step 4: Q&A Balance Check
                q_count = sum(1 for s in clip_sents if s['features']['is_question'])
                qa_ratio = q_count / len(clip_sents)
                if qa_ratio > 0.6 and best_score < 3:
                    continue # Mostly questions without strong resolution
                if q_count >= 3 and all(s['features']['is_question'] for s in clip_sents[-2:]):
                    continue # Ends on question cluster
                
                # Step 5: Minimum Quality Guard
                avg_density = np.mean([s['features']['info_density'] for s in clip_sents])
                if avg_density < 0.45:
                    continue # Reject chaotic/filler banter
                
                clean_sentence_count = sum(not s['features']['is_pivot'] for s in clip_sents)
                if clean_sentence_count < 3:
                    continue

                # Final safety
                if not clip_text_parts[0] or len(" ".join(clip_text_parts)) < 30:
                    continue

                candidates.append({
                    "type": "rolling_window",
                    "sentences": clip_sents,
                    "start": clip_sents[0]['start'],
                    "end": clip_sents[-1]['end'],
                    "text": " ".join(clip_text_parts)
                })

        # 2. Discourse-Driven Blocks with Topic Shift Guard
        for i in range(num_sents):
            start_idx = CandidateGenerator._resolve_dependency_start(sentences, i)
            if start_idx is None:
                continue

            # Trigger check (is high-signal at start or pivot point)
            trigger_f = sentences[start_idx]['features']
            f = sentences[i]['features'] # Original features for topic shift
            if trigger_f['is_question'] or trigger_f['is_strong_framing'] or f['is_strong_framing']:
                s = sentences[start_idx]
                block_sents = [s]
                current_topics = trigger_f['topics']
                
                # --- Arc tracking state for discourse block ---
                blk_has_resolution   = False
                blk_peak_emotion     = 0.0
                blk_boundary_crossed = False

                for j in range(start_idx + 1, num_sents):
                    nxt = sentences[j]
                    dur = nxt['end'] - s['start']
                    if dur > max_dur + 10: break

                    nxt_emo = nxt['features'].get('emotion_intensity', 0.0)
                    blk_peak_emotion = max(blk_peak_emotion, nxt_emo)

                    if nxt['features']['is_resolution']:
                        blk_has_resolution = True

                    # ── Hard semantic rupture ──
                    if boundary_indices and j in boundary_indices:
                        if dur < min_dur:
                            blk_boundary_crossed = True
                        else:
                            if blk_has_resolution:
                                block_sents.append(nxt)
                                break
                            blk_boundary_crossed = True  # cost, keep going

                    # ── Pivot Reset ──
                    if dur >= min_dur and nxt['features']['is_pivot']:
                        break

                    # ── Emotional decay stop ──
                    if dur >= min_dur + 8 and blk_peak_emotion > 0.65 and nxt_emo < 0.25:
                        break

                    # ── Cumulative Topic Tracking (soft signal, not hard break) ──
                    nxt_topics = nxt['features']['topics']
                    if current_topics and nxt_topics:
                        overlap = len(current_topics & nxt_topics)
                        if overlap == 0 and dur >= min_dur + 10 and blk_has_resolution:
                            # Topic drifted AND arc is complete — clean stop
                            block_sents.append(nxt)
                            break
                        current_topics |= nxt_topics

                    block_sents.append(nxt)

                    # ── Clean resolution stop (arc complete, give it room to breathe) ──
                    if blk_has_resolution and dur > min_dur + 15:
                        break
                
                if len(block_sents) > 1 and (min_dur - 5 <= (block_sents[-1]['end'] - block_sents[0]['start']) <= max_dur + 15):
                    clip_text_parts = [sent['text'] for sent in block_sents]
                    
                    # Universal Content Repair for Blocks
                    first_f = block_sents[0]['features']
                    if first_f['is_discourse_marker'] or first_f['is_continuation'] or first_f['is_acknowledgment']:
                        clip_text_parts[0] = trim_marker(clip_text_parts[0])
                    
                    # Q&A Balance Check for Blocks
                    q_count = sum(1 for sent in block_sents if sent['features']['is_question'])
                    qa_ratio = q_count / len(block_sents)
                    if qa_ratio > 0.6 and not any(sent['features']['is_resolution'] for sent in block_sents):
                        continue
                    if q_count >= 3 and all(sent['features']['is_question'] for sent in block_sents[-2:]):
                        continue

                    # Step 5: Minimum Quality Guard for Blocks
                    avg_density = np.mean([s['features']['info_density'] for s in block_sents])
                    if avg_density < 0.45:
                        continue

                    clean_sentence_count = sum(not s['features']['is_pivot'] for s in block_sents)
                    if clean_sentence_count < 3:
                        continue

                    # Safety check
                    if not clip_text_parts[0] or len(" ".join(clip_text_parts)) < 30:
                        continue

                    candidates.append({
                        "type": "discourse_block",
                        "sentences": block_sents,
                        "start": block_sents[0]['start'],
                        "end": block_sents[-1]['end'],
                        "text": " ".join(clip_text_parts)
                    })
                    
        return candidates

class LocalScorer:
    """Heuristic scoring with hook boost and clip-wide word density."""
    
    @staticmethod
    def score(candidate):
        sents = candidate['sentences']
        if not sents: return 0
        
        # 1. Hook Strength (Cap boost at 1.5)
        hook_score = min(1.5, sents[0]['features']['hook_score'] * 1.5)

        # 2. Viral Signal Density (Word-based to avoid dilution)
        total_signals = sum(
            s['features']['is_contrast'] + s['features']['is_strong_framing'] +
            s['features']['has_superlative'] + s['features']['has_number']
            for s in sents
        )
        total_words = sum(s['features']['word_count'] for s in sents)
        signal_density = min(1.0, (total_signals * 15) / total_words) if total_words > 0 else 0

        # 3. Context Independence (Soft Penalty)
        independence = 1.0 - (sents[0]['features']['context_dependency_score'] * 0.6)

        # 4. Info Density
        clip_density = np.mean([s['features']['info_density'] for s in sents])

        # 5. Emotion Intensity (avg emotional magnitude across all sentences in clip)
        emotion_boost = np.mean([s['features'].get('emotion_intensity', 0.0) for s in sents])

        # 6. Weight Rebalance: Hook 35% | Signals 25% | Emotion 25% | Independence 15%
        raw_score = (
            hook_score    * 0.35 +
            signal_density * 0.25 +
            emotion_boost  * 0.25 +
            independence   * 0.15
        )

        return raw_score * clip_density

class SemanticDeduplicator:
    """Removes overlapping candidates using fair min-duration denominator."""
    
    @staticmethod
    def deduplicate(candidates, overlap_threshold=0.7):
        if not candidates: return []
        sorted_caps = sorted(candidates, key=lambda x: x.get('local_score', 0), reverse=True)
        unique = []
        
        for cand in sorted_caps:
            is_duplicate = False
            for existing in unique:
                start_max = max(cand['start'], existing['start'])
                end_min = min(cand['end'], existing['end'])
                overlap = max(0, end_min - start_max)
                
                # Fairness: Use min duration to avoid large clips swallowing small ones
                dur_cand = cand['end'] - cand['start']
                dur_exist = existing['end'] - existing['start']
                min_dur = min(dur_cand, dur_exist)
                
                if min_dur > 0 and (overlap / min_dur) > overlap_threshold:
                    is_duplicate = True
                    break
            if not is_duplicate:
                unique.append(cand)
        return sorted(unique, key=lambda x: x['start'])

# --- Debugging & Export Helpers ---

def create_excel_download(df, filename, step_logic):
    """Creates a downloadable Excel file with data and logic sheets."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        # Sheet 1: Data
        df.to_excel(writer, index=False, sheet_name='Step Data')
        
        # Sheet 2: Process Logic
        logic_df = pd.DataFrame([{"Step Logic & Technical Details": line} for line in step_logic.split('\n')])
        logic_df.to_excel(writer, index=False, sheet_name='Process Logic')
        
        # Adjust column widths for readability
        worksheet = writer.sheets['Process Logic']
        worksheet.column_dimensions['A'].width = 100
        
    return output.getvalue()

def create_bulk_debug_zip(files_dict):
    """Creates a ZIP file containing multiple Excel reports."""
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for filename, content in files_dict.items():
            zipf.writestr(filename, content)
    return output.getvalue()

# --- Helper Functions ---

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
            return "" # Skip if only marker remains
    return text_clean

def extract_json_safely(text):
    """Safely extracts a JSON object or list from a string, even with imperfections."""
    try:
        # Find the start and end of either a list or an object
        s_obj = text.find('{')
        s_list = text.find('[')
        
        # Pick the one that appears first
        if s_obj == -1 and s_list == -1: return None
        if s_obj == -1: json_start = s_list
        elif s_list == -1: json_start = s_obj
        else: json_start = min(s_obj, s_list)
        
        # Find the corresponding end
        e_obj = text.rfind('}')
        e_list = text.rfind(']')
        
        if e_obj == -1 and e_list == -1: return None
        json_end = max(e_obj, e_list) + 1
        
        json_str = text[json_start:json_end]
        return json.loads(json_str)

    except (json.JSONDecodeError, IndexError):
        return None

def _time_string_to_seconds(ts):
    parts = ts.split('.')
    h, m, s = map(int, parts[0].split(':'))
    ms = int(parts[1]) if len(parts) > 1 else 0
    return timedelta(hours=h, minutes=m, seconds=s, milliseconds=ms).total_seconds()

def seconds_to_hms(seconds):
    seconds = int(seconds)
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"

def parse_and_process_transcript(data):
    if 'captions' not in data:
        st.error("The uploaded JSON file does not contain a 'captions' list. Please check the file format.")
        st.stop()
    raw_captions = data['captions']
    if not raw_captions: return []
    timed_captions = [{"start": _time_string_to_seconds(c['start']), "end": _time_string_to_seconds(c['end']), "text": c['text'].strip()} for c in raw_captions]
    merged = []
    if not timed_captions: return []
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

def rank_candidates_ai(candidates, client):
    """Consolidated Single-Pass AI Ranking: Scores viral potential and standalone readiness."""
    if not candidates: return []
    
    # Prepare batch text
    batch_text = ""
    for idx, cand in enumerate(candidates):
        batch_text += f"\n--- CANDIDATE {idx} (Duration: {cand['end']-cand['start']:.1f}s) ---\n{cand['text']}\n"

    system_prompt = """
You are a Viral Content Strategist. Rank these podcast clips for TikTok/Shorts.

SCORING CRITERIA (1-10):
1. viral_score: Overall punchiness and "shareability".
2. standalone_score: Can a stranger understand it with ZERO prior context?
3. resolution_score: Does the clip end on a perfect punchline/resolution?
4. context_dependency: How much does it rely on previous sentences? (1=None, 10=Total)

CRITICAL: Return ONLY valid JSON list of objects.
"""

    user_prompt = f"""
Evaluate these {len(candidates)} candidate clips:
{batch_text}

For each candidate, provide:
1. 'viral_score': Final viral potential (1-10).
2. 'standalone_score': Readiness (1-10).
3. 'resolution_score': Ending quality (1-10).
4. 'context_dependency': Context reliance (1-10).
5. 'title': Punchy headline.
6. 'hook_reason': Brief 1-sentence why.

Return ONLY a JSON list:
[
  {{
    "index": 0,
    "viral_score": 8.5,
    "standalone_score": 9.0,
    "resolution_score": 10.0,
    "context_dependency": 2,
    "title": "Title",
    "hook_reason": "Reason"
  }},
  ...
]
"""
    try:
        stream = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            model="gpt-oss-120b",
            stream=True,
            max_tokens=2500, 
            temperature=0.3
        )
        
        response_text = "".join(
            c.choices[0].delta.content or "" for c in stream
        ).strip()
        
        data = extract_json_safely(response_text)
        if isinstance(data, list):
            for item in data:
                idx = item.get('index')
                if idx is not None and 0 <= idx < len(candidates):
                    candidates[idx].update({
                        "ai_viral_score": item.get('viral_score', 0),
                        "standalone_understanding": item.get('standalone_score', 0),
                        "resolution_score": item.get('resolution_score', 0),
                        "context_dependency": item.get('context_dependency', 0),
                        "title": item.get('title', 'Untitled'),
                        "hook_reason": item.get('hook_reason', 'N/A')
                    })
            return candidates, response_text, user_prompt
        return [], response_text, user_prompt
    except Exception as e:
        st.error(f"AI Ranking failed: {e}")
        return [], str(e), user_prompt


def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default

def rank_clips_by_shorts_readiness(scored_chunks):
    """Calculates a 'final_score' for each chunk using consolidated viral metrics."""
    for clip in scored_chunks:
        viral = to_float(clip.get("ai_viral_score"))
        standalone = to_float(clip.get("standalone_understanding"))
        resolution = to_float(clip.get("resolution_score"))
        context_dep = to_float(clip.get("context_dependency"))

        # Weighted formula: Virality (40%) + Standalone (30%) + Resolution (20%) + Independence (10%)
        # Independence is (11 - context_dep) because 1 is best, 10 is worst for dependency.
        clip["final_score"] = (
            viral * 0.40 +
            standalone * 0.30 +
            resolution * 0.20 +
            (11 - context_dep) * 0.10 
        )

    return sorted(scored_chunks, key=lambda x: x.get("final_score", 0), reverse=True)



# --- Streamlit App Interface ---
st.title("🎙️ Viral Podcast Clip Finder")
st.markdown("Upload a transcript to find self-contained, hook-worthy clips (<60s) for platforms like YouTube Shorts.")

uploaded_file = st.file_uploader("Upload your transcript JSON file", type=["json"])

if uploaded_file is not None:
    try:
        key_manager = APIKeyManager(API_KEYS)
        raw_data = json.load(uploaded_file)
        
        st.markdown("--- ")
        with st.spinner("Step 1/5: Processing & standardizing transcript..."):
            transcript_data = parse_and_process_transcript(raw_data)
        st.success(f"Step 1/5: Completed - Processed transcript into {len(transcript_data)} clean segments.")


        with st.spinner("Step 2a/5: Reconstructing semantic sentences from transcript..."):
            sentences = reconstruct_sentences(transcript_data)
            st.info(f"✅ Reconstructed {len(sentences)} semantic sentences from audio.")

        with st.spinner("Step 2b/5: Computing sentence embeddings & detecting semantic boundaries…"):
            sem_model = get_semantic_model()
            embeddings = sem_model.encode([s['text'] for s in sentences], show_progress_bar=False)
            boundary_indices = set()       # soft: sim < 0.65 — used for viz / landscape only
            hard_boundary_indices = set()  # hard: sim < 0.35 — used to actually stop clip expansion
            for _bi in range(1, len(embeddings)):
                _sim = float(cosine_similarity([embeddings[_bi - 1]], [embeddings[_bi]])[0][0])
                sentences[_bi]['semantic_sim_to_prev'] = round(_sim, 4)
                if _sim < SEMANTIC_BOUNDARY_THRESHOLD:
                    boundary_indices.add(_bi)
                    sentences[_bi]['is_semantic_boundary'] = True
                else:
                    sentences[_bi]['is_semantic_boundary'] = False
                if _sim < HARD_STOP_THRESHOLD:
                    hard_boundary_indices.add(_bi)
            sentences[0]['semantic_sim_to_prev'] = 1.0
            sentences[0]['is_semantic_boundary'] = False
            st.info(f"✅ Detected {len(boundary_indices)} soft boundaries (viz) | {len(hard_boundary_indices)} hard stop boundaries (clip cuts).")

        with st.spinner("Step 2c/5: Scoring emotional intensity per sentence…"):
            emo_model = get_emotion_model()
            emo_texts = [s['text'][:400] for s in sentences]
            emo_results = emo_model(emo_texts, batch_size=16, truncation=True)

            for s, res in zip(sentences, emo_results):
                s['features']['emotion_intensity'] = round(abs(res['score'] - 0.5) * 2, 4)
            st.info(f"✅ Emotion intensity scored for all {len(sentences)} sentences.")

        with st.spinner("Step 2d/5: Generating boundary-aware candidates…"):
            raw_candidates = CandidateGenerator.generate(
                sentences, boundary_indices=hard_boundary_indices  # only hard topic shifts stop expansion
            )
            st.info(f"Generated {len(raw_candidates)} candidate clips using O(n) sliding window & hard semantic boundaries.")

            # Local Pre-Scoring (now includes emotion_boost)
            for cand in raw_candidates:
                cand['local_score'] = LocalScorer.score(cand)

            # Deduplicate
            unique_candidates = SemanticDeduplicator.deduplicate(raw_candidates)
            st.success(f"Deduplicated to {len(unique_candidates)} high-potential candidates.")

            # AI Ranking (Top 25, Batched)
            top_candidates = sorted(unique_candidates, key=lambda x: x['local_score'], reverse=True)[:25]
            candidate_chunks = []

            batch_size = 6
            for i in range(0, len(top_candidates), batch_size):
                batch = top_candidates[i : i + batch_size]
                st.write(f"🤖 Analyzing batch {i//batch_size + 1} ({len(batch)} clips)...")
                client = key_manager.get_client()
                ranked_batch, raw_ai, full_prompt = rank_candidates_ai(batch, client)
                candidate_chunks.extend(ranked_batch)
                print(f"\nBATCH {i//batch_size + 1} AI RESPONSE:\n{raw_ai}\n")

        st.success(f"Step 2-3/5: Identified and scored {len(candidate_chunks)} viral candidates.")


        if candidate_chunks:
            with st.spinner("Step 4/5: Ranking clips by production quality..."):
                ranked_clips = rank_clips_by_shorts_readiness(candidate_chunks)
            st.success("Step 4/5: Completed - Clips are ranked.")

            # --- TECHNICAL DEBUGGING SECTION ---
            st.markdown("---")
            with st.expander("🛠️ TECHNICAL DEBUGGING: Step-by-Step Pipeline Trace"):
                st.markdown("Download the internal data and exact logic applied at each stage of the pipeline.")
                
                col1, col2 = st.columns(2)
                col3, col4 = st.columns(2)

                # Step 1 Logic
                step1_logic = """STEP 1: TRANSCRIPTION PREPROCESSING
1. Raw JSON Input: Reads the 'captions' list from the uploaded file.
2. Timestamp Normalization: Converts HH:MM:SS.ms strings to float seconds using _time_string_to_seconds.
3. Deduplication: Iterates through captions. If a caption text is identical to or starts with the previous text, their durations are merged.
4. Result: A clean list of timed text segments ready for NLP analysis."""
                
                # Step 2 Logic
                step2_logic = """STEP 2: NLP ENRICHMENT + SEMANTIC EMBEDDING + EMOTION SCORING
1. Sentence Reconstruction: Uses spaCy to group caption fragments into grammatical sentences.
2. Timestamp Alignment: Maps sentence character offsets back to caption timestamps.
3. Feature Detection (SentenceFeatureDetector):
   - Hook Score, Context Dependency, Viral Signals (numbers, entities, superlatives).
4. Semantic Embedding (all-MiniLM-L6-v2 on D drive):
   - Each sentence encoded into a 384-dim vector.
   - DUAL THRESHOLD SYSTEM:
     * Soft boundary  (sim < 0.65): marked as is_semantic_boundary=True for viz/energy map ONLY.
     * Hard stop      (sim < 0.35): actually stops clip expansion — only true dramatic topic shifts.
   - Podcast speech naturally has sim=0.1–0.4 between sentences; the soft threshold captures all
     detectable shifts while the hard threshold prevents premature cuts on coherent conversations.
5. Emotion Intensity (cardiffnlp/twitter-roberta-base-sentiment on D drive):
   - intensity = abs(model_confidence - 0.5) * 2  [0=neutral, 1=extreme]
Result: Each sentence has NLP features + semantic_sim_to_prev + is_semantic_boundary + emotion_intensity."""

                # Step 3 Logic
                step3_logic = """STEP 3: CANDIDATE GENERATION — ARC COMPLETION MODE
1. Sliding Window: Scans for valid starts (Non-pivots, non-fragments).
2. Backtracking: Dependency starts (e.g. 'So...') backtrack to strong anchor.
3. Arc Tracking state per candidate:
   - has_resolution: True if ANY sentence in the arc is a resolution (accumulates forward).
   - peak_emotion: Maximum emotion_intensity seen so far in the arc.
   - boundary_crossed: True if a hard rupture (sim < 0.25) was crossed mid-arc.
4. Stop Conditions (priority order):
   a. dur > 65s (hard cap)
   b. Pivot sentence hit after min_dur (structural break)
   c. Emotional decay: peak > 0.65 AND current < 0.25, after 38s
   d. Hard rupture (sim < 0.25) AND has_resolution: arc complete, stop cleanly.
   e. Hard rupture (sim < 0.25) AND no resolution: note cost, KEEP EXPANDING.
5. Boundary = COST, not kill-switch: boundary_crossed demotes clip score by 1 tier.
6. Questions are NOT stop signals — clips expand through full Q&A exchanges.
7. Discourse Blocks: same arc logic; topic drift stops only when arc is also resolved.
Result: Clips naturally land at 38-58s instead of collapsing to 30s."""

                # Step 4 Logic
                step4_logic = """STEP 4: SCORING & DEDUPLICATION
1. Local Scoring (LocalScorer) - weights:
   - Hook Boost:      35% weight
   - Signal Density:  25% weight (1 signal / 15 words = gold)
   - Emotion Boost:   25% weight (avg emotion intensity across clip)
   - Independence:    15% weight
2. Deduplication: Removes overlapping candidates (>70% overlap).
Result: The best version of every clip, ready for AI ranking."""

                # Step 5 Logic (NEW)
                step5_logic = """STEP 5: SEMANTIC & ENERGY MAP
Row-by-row breakdown of every sentence in the transcript:
- semantic_sim_to_prev: cosine similarity to previous sentence (0-1, lower = bigger topic shift)
- is_semantic_boundary: True if similarity < 0.65 (SOFT — visualization only, does NOT stop clips)
- emotion_intensity: abs(model_confidence - 0.5)*2  (0=neutral, 1=extreme emotional spike)
- is_energy_spike: True if emotion_intensity > 0.70
Note: Clip expansion only hard-stops at catastrophic ruptures (sim < 0.25). Soft boundaries are colour-coded here for auditing.
Use this to audit WHY the system respected or crossed certain sentence boundaries."""

                with col1:
                    st.info("**Step 1: Clean Transcript**")
                    df_step1 = pd.DataFrame(transcript_data)
                    st.download_button("📥 Download Step 1 Excel", create_excel_download(df_step1, "step1_preprocessing.xlsx", step1_logic), "step1_preprocessing.xlsx", key="dl_step1")

                with col2:
                    st.info("**Step 2: Enriched Sentences + Semantic + Emotion**")
                    # Flatten features + add semantic/emotion top-level cols
                    step2_data = []
                    for s in sentences:
                        row = {"text": s['text'], "start": s['start'], "end": s['end']}
                        row.update(s['features'])
                        row['semantic_sim_to_prev'] = s.get('semantic_sim_to_prev', 1.0)
                        row['is_semantic_boundary'] = s.get('is_semantic_boundary', False)
                        # Convert set to str for Excel
                        if 'topics' in row and isinstance(row['topics'], set):
                            row['topics'] = ', '.join(sorted(row['topics']))
                        step2_data.append(row)
                    df_step2 = pd.DataFrame(step2_data)
                    st.download_button("📥 Download Step 2 Excel", create_excel_download(df_step2, "step2_nlp_enrichment.xlsx", step2_logic), "step2_nlp_enrichment.xlsx", key="dl_step2")

                with col3:
                    st.info("**Step 3: All Raw Candidates**")
                    step3_data = [{"text": c['text'], "start": c['start'], "end": c['end'], "type": c['type']} for c in raw_candidates]
                    df_step3 = pd.DataFrame(step3_data)
                    st.download_button("📥 Download Step 3 Excel", create_excel_download(df_step3, "step3_chunking.xlsx", step3_logic), "step3_chunking.xlsx", key="dl_step3")

                with col4:
                    st.info("**Step 4: Final Candidates (Deduplicated)**")
                    step4_data = [{"text": c['text'], "start": c['start'], "end": c['end'], "local_score": c['local_score']} for c in unique_candidates]
                    df_step4 = pd.DataFrame(step4_data)
                    st.download_button("📥 Download Step 4 Excel", create_excel_download(df_step4, "step4_final_candidates.xlsx", step4_logic), "step4_final_candidates.xlsx", key="dl_step4")

                # Step 5: Semantic & Energy Map (full-width)
                st.markdown("---")
                st.info("**Step 5: Semantic & Energy Map (NEW)**")
                step5_data = []
                for idx, s in enumerate(sentences):
                    emo = s['features'].get('emotion_intensity', 0.0)
                    step5_data.append({
                        "sentence_idx": idx,
                        "text": s['text'],
                        "start": round(s['start'], 2),
                        "end": round(s['end'], 2),
                        "semantic_sim_to_prev": s.get('semantic_sim_to_prev', 1.0),
                        "is_semantic_boundary": s.get('is_semantic_boundary', False),
                        "emotion_intensity": emo,
                        "is_energy_spike": emo > 0.70,
                    })
                df_step5 = pd.DataFrame(step5_data)
                st.download_button(
                    "🧠 Download Step 5: Semantic & Energy Map Excel",
                    create_excel_download(df_step5, "step5_semantic_energy.xlsx", step5_logic),
                    "step5_semantic_energy.xlsx",
                    key="dl_step5",
                    use_container_width=True
                )

            st.balloons()

            # --- 🧠 SEMANTIC LANDSCAPE EXPANDER (new) ---
            st.markdown("---")
            with st.expander("🧠 Semantic Landscape & Energy Map", expanded=False):
                st.markdown("Every sentence in the transcript — colour-coded by **emotion intensity** and **semantic boundaries**.")
                st.caption("🔴 Red row = semantic boundary (topic shift)  |  ⚡ = energy spike (emotion > 0.70)")
                landscape_rows = []
                for s in sentences:
                    emo = s['features'].get('emotion_intensity', 0.0)
                    is_bnd = s.get('is_semantic_boundary', False)
                    sim = s.get('semantic_sim_to_prev', 1.0)
                    landscape_rows.append({
                        "Start": f"{int(s['start']//60)}:{int(s['start']%60):02d}",
                        "Tags": ("🔴 BOUNDARY " if is_bnd else "") + ("⚡ SPIKE" if emo > 0.70 else ""),
                        "Sim↔Prev": f"{sim:.2f}",
                        "Emotion": f"{emo:.2f}",
                        "Text": s['text'],
                    })
                df_landscape = pd.DataFrame(landscape_rows)

                def _color_row(row):
                    if "BOUNDARY" in str(row['Tags']):
                        return ['background-color: #3d0000; color: #ff6b6b'] * len(row)
                    if "SPIKE" in str(row['Tags']):
                        return ['background-color: #2d2d00; color: #ffd700'] * len(row)
                    return [''] * len(row)

                st.dataframe(
                    df_landscape.style.apply(_color_row, axis=1),
                    use_container_width=True, height=400
                )

            st.header("📈 Analysis Complete")
            
            # --- ONE-CLICK BULK DOWNLOAD (Logic defined here to include CSV later) ---
            # We'll compute the CSV first and then show the ZIP button
            if ranked_clips:
                df = pd.DataFrame(ranked_clips)
                df['start_timestamp'] = df['start'].apply(lambda s: f"{int(s // 60)}:{int(s % 60):02d}")
                df['end_timestamp'] = df['end'].apply(lambda s: f"{int(s // 60)}:{int(s % 60):02d}")
                
                csv_cols = ['final_score', 'title', 'hook_reason', 'start_timestamp', 'end_timestamp', 'text', 'ai_viral_score', 'standalone_understanding', 'resolution_score', 'context_dependency', 'local_score']
                df_display = df.reindex(columns=csv_cols).fillna('N/A')
                csv_encoded = df_display.to_csv(index=False).encode('utf-8')

                # Prepare the Bulk Zip for One-Click Download
                all_files_for_zip = {
                    "step1_preprocessing.xlsx": create_excel_download(pd.DataFrame(transcript_data), "step1_preprocessing.xlsx", step1_logic),
                    "step2_nlp_enrichment.xlsx": create_excel_download(pd.DataFrame(step2_data), "step2_nlp_enrichment.xlsx", step2_logic),
                    "step3_chunking.xlsx": create_excel_download(pd.DataFrame(step3_data), "step3_chunking.xlsx", step3_logic),
                    "step4_final_candidates.xlsx": create_excel_download(pd.DataFrame(step4_data), "step4_final_candidates.xlsx", step4_logic),
                    "step5_semantic_energy.xlsx": create_excel_download(pd.DataFrame(step5_data), "step5_semantic_energy.xlsx", step5_logic),
                    "viral_clips_analysis.csv": csv_encoded
                }
                master_zip = create_bulk_debug_zip(all_files_for_zip)
                
                st.success("✨ **Master Download Ready!** Grab all technical logs and the final ranking in one click.")
                st.download_button(
                    label="🗳️ DOWNLOAD ALL FILES (Excel Logs + CSV Results)",
                    data=master_zip,
                    file_name="viral_pipeline_full_export.zip",
                    mime="application/zip",
                    use_container_width=True
                )
                st.markdown("---")

            st.markdown("Downloads are ready. Preview the top clips below.")

            if ranked_clips:
                df = pd.DataFrame(ranked_clips)
                df['start_timestamp'] = df['start'].apply(lambda s: f"{int(s // 60)}:{int(s % 60):02d}")
                df['end_timestamp'] = df['end'].apply(lambda s: f"{int(s // 60)}:{int(s % 60):02d}")
                
                csv_cols = [
                        'final_score',
                        'title',
                        'hook_reason',
                        'start_timestamp',
                        'end_timestamp',
                        'text',
                        'ai_viral_score',
                        'standalone_understanding',
                        'resolution_score',
                        'context_dependency',
                        'local_score'
                ]
                df_display = df.reindex(columns=csv_cols).fillna('N/A')
                
                st.download_button("📥 Download All as CSV", df_display.to_csv(index=False).encode('utf-8'), "viral_clips_analysis.csv", "text/csv")

                st.header("🏆 Top Viral Clip Candidates (Ranked by Hook)")
                for i, clip in enumerate(ranked_clips):
                    clip_sents = clip.get('sentences', [])
                    avg_emo = np.mean([s['features'].get('emotion_intensity', 0.0) for s in clip_sents]) if clip_sents else 0.0
                    n_boundaries = sum(1 for s in clip_sents if s.get('is_semantic_boundary', False))
                    dur = clip['end'] - clip['start']
                    viral_score = clip.get('ai_viral_score', 0)

                    # Color-coded tier badge
                    if viral_score >= 8:
                        badge = "🔥 VIRAL TIER"
                    elif viral_score >= 6:
                        badge = "⚡ HIGH POTENTIAL"
                    else:
                        badge = "📌 CANDIDATE"

                    st.markdown(f"### Rank #{i+1}  {badge}")
                    col_a, col_b, col_c, col_d = st.columns(4)
                    col_a.metric("Final Score", f"{clip.get('final_score', 0):.2f}")
                    col_b.metric("AI Viral", f"{viral_score:.1f}/10")
                    col_c.metric("Duration", f"{dur:.0f}s")
                    col_d.metric("Semantic Boundaries", n_boundaries)

                    st.markdown(
                        f"**⏱ Timestamp:** `{int(clip['start']//60)}:{int(clip['start']%60):02d}` → "
                        f"`{int(clip['end']//60)}:{int(clip['end']%60):02d}`  |  "
                        f"**🎯 Hook:** {clip.get('hook_reason', 'N/A')}"
                    )

                    # Emotion intensity bar
                    emo_pct = min(1.0, avg_emo)
                    emo_label = "🟢 Calm" if emo_pct < 0.35 else ("🟡 Charged" if emo_pct < 0.65 else "🔴 High Intensity")
                    st.markdown(f"**⚡ Avg Emotion Intensity:** {emo_label} ({emo_pct:.0%})")
                    st.progress(emo_pct)

                    with st.expander(f"📄 Transcript — {clip.get('title', 'Untitled')}"):
                        # Highlight semantic boundaries within the clip text
                        highlighted_parts = []
                        for s in clip_sents:
                            txt = s['text']
                            if s.get('is_semantic_boundary', False):
                                highlighted_parts.append(f"[🔴 SHIFT] {txt}")
                            elif s['features'].get('emotion_intensity', 0) > 0.70:
                                highlighted_parts.append(f"[⚡ SPIKE] {txt}")
                            else:
                                highlighted_parts.append(txt)
                        st.text_area(
                            "Transcript (🔴=semantic shift, ⚡=emotion spike)",
                            "\n".join(highlighted_parts),
                            height=180,
                            key=f"text_{i}"
                        )
                        st.caption(
                            f"Standalone: {clip.get('standalone_understanding',0):.1f}/10  |  "
                            f"Resolution: {clip.get('resolution_score',0):.1f}/10  |  "
                            f"Context Dep: {clip.get('context_dependency',0):.0f}/10  |  "
                            f"Local Score: {clip.get('local_score',0):.3f}"
                        )
                    st.markdown("---")
            else:
                st.warning("Analysis ran, but no clips were successfully scored.")
        else:
            st.warning("AI Scouting did not identify any viral clips matching the 30-60s criteria.")
            st.info("💡 **Check the Sidebar (Left)**: Expand the '🔍 Debug' sections to see the AI's raw thoughts and why certain clips failed to align.")
    except Exception as e:
        st.error(f"A critical error occurred. Please see details below.")
        st.code(traceback.format_exc())
else:
    st.info("Awaiting transcript file upload.")
