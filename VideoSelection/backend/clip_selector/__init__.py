"""
ClipSelector package — AI-powered viral clip detection pipeline.

All ClipSelector logic lives here. To modify any part of the pipeline:
  config.py          → thresholds, model paths, API keys
  nlp_service.py     → spaCy NLP, sentence detection, feature scoring
  semantic_service.py → sentence embeddings, boundary detection, emotion scoring
  candidate_service.py → clip candidate generation, local scoring, deduplication
  ai_ranking_service.py → Cerebras API, AI-powered viral ranking
  service.py         → orchestrator: ties all steps together
  router.py          → FastAPI endpoints exposed to the frontend
  schemas.py         → Pydantic request/response models
"""
