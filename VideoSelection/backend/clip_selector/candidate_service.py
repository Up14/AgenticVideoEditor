"""
Candidate Service — clip candidate generation, local scoring, deduplication, and final ranking.

Verbatim port of CandidateGenerator, LocalScorer, SemanticDeduplicator, and
rank_clips_by_shorts_readiness from ExistingCode/ClipSelector/app.py.
Zero modifications to any business logic.
"""

import numpy as np
from clip_selector.nlp_service import trim_marker


# ---------------------------------------------------------------------------
# to_float (lines 797-801 of app.py — unchanged)
# ---------------------------------------------------------------------------
def to_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# CandidateGenerator (lines 262-540 of app.py — unchanged)
# ---------------------------------------------------------------------------
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
            return None  # Can't backtrack at start of text

        # Hard Reject for "But..." starts (unless it's an acknowledgment "no, but")
        text_lower = sentences[i]['text'].lower().strip()
        if text_lower.startswith("but "):
            return None

        prev = sentences[i - 1]
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
            return i - 1  # Backtrack ONE step

        return None  # Skip weak dependency start

    @staticmethod
    def generate(sentences, min_dur=30, max_dur=65, boundary_indices=None):
        candidates = []
        if not sentences:
            return candidates
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
                if dur > max_dur:
                    break

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
                        clip_so_far = sentences[start_idx:j + 1]
                        q_count_so_far = sum(1 for s in clip_so_far if s['features']['is_question'])
                        if q_count_so_far >= 2:  # lower bar: even 2 Qs means answer likely coming
                            ans_words = 0
                            for k in range(j, start_idx - 1, -1):
                                if sentences[k]['features']['is_question']:
                                    break
                                ans_words += sentences[k]['features']['word_count']
                            if ans_words < 15:
                                score = 0  # Force lookahead until answer is substantial

                    if score > best_score or (score == best_score and j >= best_end):
                        best_score = score
                        best_end = j

                    # Only early-exit on a strong resolution that has time to breathe
                    if has_resolution and best_score == 3 and dur > min_dur + 15:
                        break

            if best_end != -1:
                clip_sents = sentences[start_idx:best_end + 1]

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
                    continue  # Mostly questions without strong resolution
                if q_count >= 3 and all(s['features']['is_question'] for s in clip_sents[-2:]):
                    continue  # Ends on question cluster

                # Step 5: Minimum Quality Guard
                avg_density = np.mean([s['features']['info_density'] for s in clip_sents])
                if avg_density < 0.45:
                    continue  # Reject chaotic/filler banter

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
            f = sentences[i]['features']  # Original features for topic shift
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
                    if dur > max_dur + 10:
                        break

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


# ---------------------------------------------------------------------------
# LocalScorer (lines 542-579 of app.py — unchanged)
# ---------------------------------------------------------------------------
class LocalScorer:
    """Heuristic scoring with hook boost and clip-wide word density."""

    @staticmethod
    def score(candidate):
        sents = candidate['sentences']
        if not sents:
            return 0

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
            hook_score     * 0.35 +
            signal_density * 0.25 +
            emotion_boost  * 0.25 +
            independence   * 0.15
        )

        return raw_score * clip_density


# ---------------------------------------------------------------------------
# SemanticDeduplicator (lines 581-607 of app.py — unchanged)
# ---------------------------------------------------------------------------
class SemanticDeduplicator:
    """Removes overlapping candidates using fair min-duration denominator."""

    @staticmethod
    def deduplicate(candidates, overlap_threshold=0.7):
        if not candidates:
            return []
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


# ---------------------------------------------------------------------------
# rank_clips_by_shorts_readiness (lines 803-820 of app.py — unchanged)
# ---------------------------------------------------------------------------
def rank_clips_by_shorts_readiness(scored_chunks):
    """Calculates a 'final_score' for each chunk using consolidated viral metrics."""
    for clip in scored_chunks:
        viral      = to_float(clip.get("ai_viral_score"))
        standalone = to_float(clip.get("standalone_understanding"))
        resolution = to_float(clip.get("resolution_score"))
        context_dep = to_float(clip.get("context_dependency"))

        # Weighted formula: Virality (40%) + Standalone (30%) + Resolution (20%) + Independence (10%)
        # Independence is (11 - context_dep) because 1 is best, 10 is worst for dependency.
        clip["final_score"] = (
            viral       * 0.40 +
            standalone  * 0.30 +
            resolution  * 0.20 +
            (11 - context_dep) * 0.10
        )

    return sorted(scored_chunks, key=lambda x: x.get("final_score", 0), reverse=True)
