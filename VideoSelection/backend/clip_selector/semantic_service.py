"""
Semantic Service — sentence embedding, boundary detection, and emotion scoring.
Part of the clip_selector package.
"""

import logging
from sklearn.metrics.pairwise import cosine_similarity
from clip_selector.config import (
    MODELS_DIR,
    SEMANTIC_BOUNDARY_THRESHOLD,
    HARD_STOP_THRESHOLD,
)

logger = logging.getLogger(__name__)

_semantic_model = None
_emotion_model = None


def get_semantic_model():
    """Loads all-MiniLM-L6-v2. Downloads to D:\\models on first run, uses cache after."""
    global _semantic_model
    if _semantic_model is None:
        logger.info("Loading Semantic Model (all-MiniLM-L6-v2) → %s ...", MODELS_DIR)
        from sentence_transformers import SentenceTransformer
        _semantic_model = SentenceTransformer("all-MiniLM-L6-v2", cache_folder=MODELS_DIR)
        logger.info("Semantic model loaded.")
    return _semantic_model


def get_emotion_model():
    """
    Loads Cardiff NLP twitter-roberta-base-sentiment to D:\\models.
    Uses AutoTokenizer + AutoModelForSequenceClassification so cache_dir
    only applies at load-time and never leaks into tokenizer inference calls.
    """
    global _emotion_model
    if _emotion_model is None:
        logger.info("Loading Emotion Model (cardiffnlp/twitter-roberta-base-sentiment) → %s ...", MODELS_DIR)
        from transformers import (
            AutoTokenizer,
            AutoModelForSequenceClassification,
            pipeline as hf_pipeline,
        )
        _name = "cardiffnlp/twitter-roberta-base-sentiment"
        _tok = AutoTokenizer.from_pretrained(_name, cache_dir=MODELS_DIR)
        _mdl = AutoModelForSequenceClassification.from_pretrained(_name, cache_dir=MODELS_DIR)
        _emotion_model = hf_pipeline("sentiment-analysis", model=_mdl, tokenizer=_tok)
        logger.info("Emotion model loaded.")
    return _emotion_model


def compute_embeddings_and_boundaries(sentences):
    """
    Encodes sentences into embeddings, computes cosine similarity between
    consecutive sentences, and classifies soft/hard semantic boundaries.

    Returns:
        Tuple of (sentences, boundary_indices, hard_boundary_indices)
    """
    sem_model = get_semantic_model()
    embeddings = sem_model.encode(
        [s['text'] for s in sentences],
        show_progress_bar=False
    )

    boundary_indices = set()       # soft: sim < 0.65 — used for viz / landscape only
    hard_boundary_indices = set()  # hard: sim < 0.25 — stops clip expansion

    for bi in range(1, len(embeddings)):
        sim = float(cosine_similarity([embeddings[bi - 1]], [embeddings[bi]])[0][0])
        sentences[bi]['semantic_sim_to_prev'] = round(sim, 4)
        if sim < SEMANTIC_BOUNDARY_THRESHOLD:
            boundary_indices.add(bi)
            sentences[bi]['is_semantic_boundary'] = True
        else:
            sentences[bi]['is_semantic_boundary'] = False
        if sim < HARD_STOP_THRESHOLD:
            hard_boundary_indices.add(bi)

    sentences[0]['semantic_sim_to_prev'] = 1.0
    sentences[0]['is_semantic_boundary'] = False

    logger.info(
        "Boundaries — soft: %d | hard: %d",
        len(boundary_indices), len(hard_boundary_indices)
    )
    return sentences, boundary_indices, hard_boundary_indices


def score_emotion_intensity(sentences):
    """
    Scores emotional intensity for every sentence using the Cardiff NLP model.
    intensity = abs(model_confidence - 0.5) * 2  → [0=neutral, 1=extreme]

    Mutates sentences in-place: adds 'emotion_intensity' to each sentence's features.
    """
    emo_model = get_emotion_model()
    emo_texts = [s['text'][:400] for s in sentences]
    emo_results = emo_model(emo_texts, batch_size=16, truncation=True)

    for s, res in zip(sentences, emo_results):
        s['features']['emotion_intensity'] = round(abs(res['score'] - 0.5) * 2, 4)

    logger.info("Emotion intensity scored for %d sentences.", len(sentences))
