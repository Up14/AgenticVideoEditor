"""
Configuration constants for the ClipSelector pipeline.
API keys are loaded from .env — never hardcoded here.
"""

import os
from dotenv import load_dotenv

# Load .env from the backend root (two levels up from clip_selector/)
_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
load_dotenv(_env_path)

# ---------------------------------------------------------------------------
# Model storage — configurable via .env, defaults to ~/.cache/videdi_models
# so it works on any machine regardless of OS or drive letters.
# ---------------------------------------------------------------------------
_default_models_dir = os.path.join(os.path.expanduser("~"), ".cache", "videdi_models")
MODELS_DIR = os.getenv("MODELS_DIR", _default_models_dir)
os.makedirs(MODELS_DIR, exist_ok=True)

# ---------------------------------------------------------------------------
# Semantic boundary thresholds (same values as original app.py)
# ---------------------------------------------------------------------------
SEMANTIC_BOUNDARY_THRESHOLD = 0.65   # cosine sim drop below this → boundary in viz
HARD_STOP_THRESHOLD = 0.25           # catastrophic topic rupture only

# ---------------------------------------------------------------------------
# Cerebras API keys
# ---------------------------------------------------------------------------
_raw_keys = os.getenv("CEREBRAS_API_KEYS", "")
CEREBRAS_API_KEYS = [k.strip() for k in _raw_keys.split(",") if k.strip()]

if not CEREBRAS_API_KEYS:
    raise RuntimeError(
        "No CEREBRAS_API_KEYS found. "
        "Please set CEREBRAS_API_KEYS in backend/.env as a comma-separated list."
    )
