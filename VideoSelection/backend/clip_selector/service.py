"""
Clip Selector Orchestrator — runs the full viral clip pipeline end-to-end.
Part of the clip_selector package. Edit this file to change the pipeline flow.
"""

import logging
from typing import Any

from services.caption_service import get_captions
from clip_selector.nlp_service import (
    parse_and_process_transcript,
    reconstruct_sentences,
)
from clip_selector.semantic_service import (
    compute_embeddings_and_boundaries,
    score_emotion_intensity,
)
from clip_selector.candidate_service import (
    CandidateGenerator,
    LocalScorer,
    SemanticDeduplicator,
    rank_clips_by_shorts_readiness,
    to_float,
)
from clip_selector.ai_ranking_service import (
    rank_candidates_ai,
    get_key_manager,
)

logger = logging.getLogger(__name__)

_BATCH_SIZE = 6


def _seconds_to_timestamp(seconds: float) -> str:
    seconds = max(0, int(seconds))
    m = seconds // 60
    s = seconds % 60
    return f"{m}:{s:02d}"


def _serialize_clip(clip: dict) -> dict[str, Any]:
    """Strip non-JSON-serializable data and return a clean dict for the API response."""
    start = clip.get("start", 0.0)
    end   = clip.get("end", 0.0)
    return {
        "title":                   clip.get("title", "Untitled"),
        "hook_reason":             clip.get("hook_reason", "N/A"),
        "start":                   round(start, 3),
        "end":                     round(end, 3),
        "duration":                round(end - start, 3),
        "start_timestamp":         _seconds_to_timestamp(start),
        "end_timestamp":           _seconds_to_timestamp(end),
        "text":                    clip.get("text", ""),
        "final_score":             round(to_float(clip.get("final_score")), 4),
        "ai_viral_score":          round(to_float(clip.get("ai_viral_score")), 2),
        "standalone_understanding": round(to_float(clip.get("standalone_understanding")), 2),
        "resolution_score":        round(to_float(clip.get("resolution_score")), 2),
        "context_dependency":      round(to_float(clip.get("context_dependency")), 2),
        "local_score":             round(to_float(clip.get("local_score")), 4),
    }


def run_clip_selector(video_id: str) -> list[dict[str, Any]]:
    """
    Full ClipSelector pipeline for a given video_id.

    Reads captions.json from disk (written by the /api/process endpoint),
    runs the complete NLP → semantic → emotion → candidate → AI ranking pipeline,
    and returns a list of ranked clip dicts ready for JSON serialization.
    """

    # Step 1: Load captions from disk
    logger.info("[%s] Step 1/5: Loading captions from disk...", video_id)
    captions_data = get_captions(video_id)
    if not captions_data:
        raise ValueError(
            f"No captions found for video_id='{video_id}'. "
            "Please run /api/process first."
        )

    # Step 2a: Parse & standardize transcript
    logger.info("[%s] Step 2a/5: Parsing transcript...", video_id)
    transcript_data = parse_and_process_transcript(captions_data)
    if not transcript_data:
        raise ValueError(f"Transcript for video_id='{video_id}' is empty after parsing.")
    logger.info("[%s] %d clean segments.", video_id, len(transcript_data))

    # Step 2b: Reconstruct semantic sentences
    logger.info("[%s] Step 2b/5: Reconstructing sentences...", video_id)
    sentences = reconstruct_sentences(transcript_data)
    logger.info("[%s] %d sentences.", video_id, len(sentences))

    # Step 2c: Semantic embeddings & boundary detection
    logger.info("[%s] Step 2c/5: Embeddings + boundary detection...", video_id)
    sentences, boundary_indices, hard_boundary_indices = compute_embeddings_and_boundaries(sentences)

    # Step 2d: Emotion intensity scoring
    logger.info("[%s] Step 2d/5: Emotion scoring...", video_id)
    score_emotion_intensity(sentences)

    # Step 3: Generate candidates
    logger.info("[%s] Step 3/5: Generating candidates...", video_id)
    raw_candidates = CandidateGenerator.generate(
        sentences,
        boundary_indices=hard_boundary_indices
    )
    logger.info("[%s] %d raw candidates.", video_id, len(raw_candidates))

    for cand in raw_candidates:
        cand['local_score'] = LocalScorer.score(cand)

    unique_candidates = SemanticDeduplicator.deduplicate(raw_candidates)
    logger.info("[%s] %d unique candidates.", video_id, len(unique_candidates))

    # Step 4: AI Ranking (top 25, batch_size=6)
    logger.info("[%s] Step 4/5: AI ranking...", video_id)
    top_candidates = sorted(unique_candidates, key=lambda x: x['local_score'], reverse=True)[:25]
    candidate_chunks = []
    key_manager = get_key_manager()

    for i in range(0, len(top_candidates), _BATCH_SIZE):
        batch = top_candidates[i: i + _BATCH_SIZE]
        logger.info("[%s] Batch %d (%d clips)...", video_id, i // _BATCH_SIZE + 1, len(batch))
        client = key_manager.get_client()
        ranked_batch, _, _ = rank_candidates_ai(batch, client)
        candidate_chunks.extend(ranked_batch)

    # Step 5: Final ranking
    logger.info("[%s] Step 5/5: Final ranking...", video_id)
    ranked_clips = rank_clips_by_shorts_readiness(candidate_chunks)

    result = [_serialize_clip(c) for c in ranked_clips]
    logger.info("[%s] Done — %d ranked clips.", video_id, len(result))
    return result
