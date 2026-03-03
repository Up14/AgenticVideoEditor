"""
AI Ranking Service — Cerebras API key management and AI-powered clip ranking.
Part of the clip_selector package.
"""

import json
import time
import logging
from itertools import cycle

from cerebras.cloud.sdk import Cerebras
from clip_selector.config import CEREBRAS_API_KEYS

logger = logging.getLogger(__name__)


def extract_json_safely(text):
    """Safely extracts a JSON object or list from a string, even with imperfections."""
    try:
        s_obj  = text.find('{')
        s_list = text.find('[')

        if s_obj == -1 and s_list == -1: return None
        if s_obj == -1:    json_start = s_list
        elif s_list == -1: json_start = s_obj
        else:              json_start = min(s_obj, s_list)

        e_obj  = text.rfind('}')
        e_list = text.rfind(']')

        if e_obj == -1 and e_list == -1: return None
        json_end = max(e_obj, e_list) + 1

        return json.loads(text[json_start:json_end])

    except (json.JSONDecodeError, IndexError):
        return None


class APIKeyManager:
    """Manages API keys, client rotation, and rate limiting."""

    def __init__(self, api_keys, rate_limit=28, period_seconds=60):
        if not api_keys:
            raise RuntimeError("No API keys provided. Check CEREBRAS_API_KEYS in .env.")
        self.clients    = {key: Cerebras(api_key=key) for key in api_keys}
        self.key_cycler = cycle(api_keys)
        self.usage      = {key: [] for key in api_keys}
        self.rate_limit = rate_limit
        self.period     = period_seconds
        self.key_count  = len(api_keys)

    def get_client(self):
        checked_keys = 0
        while checked_keys < self.key_count:
            current_key = next(self.key_cycler)
            now = time.monotonic()
            self.usage[current_key] = [
                ts for ts in self.usage[current_key] if now - ts < self.period
            ]
            if len(self.usage[current_key]) < self.rate_limit:
                self.usage[current_key].append(now)
                return self.clients[current_key]
            checked_keys += 1

        oldest_ts  = min(min(ts) for ts in self.usage.values() if ts)
        sleep_time = self.period - (time.monotonic() - oldest_ts) + 1.5
        logger.warning(
            "All API keys are rate-limited. Waiting %.1fs for refresh...", sleep_time
        )
        time.sleep(sleep_time)
        return self.get_client()


def rank_candidates_ai(candidates, client):
    """Consolidated Single-Pass AI Ranking: Scores viral potential and standalone readiness."""
    if not candidates:
        return [], "", ""

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
                {"role": "user",   "content": user_prompt}
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
                        "ai_viral_score":          item.get('viral_score', 0),
                        "standalone_understanding": item.get('standalone_score', 0),
                        "resolution_score":         item.get('resolution_score', 0),
                        "context_dependency":       item.get('context_dependency', 0),
                        "title":                    item.get('title', 'Untitled'),
                        "hook_reason":              item.get('hook_reason', 'N/A')
                    })
            return candidates, response_text, user_prompt

        logger.error("AI ranking returned unexpected format: %s", response_text[:200])
        return [], response_text, user_prompt

    except Exception as e:
        logger.exception("AI Ranking failed")
        raise RuntimeError(f"AI Ranking failed: {e}") from e


_key_manager = None

def get_key_manager() -> APIKeyManager:
    global _key_manager
    if _key_manager is None:
        _key_manager = APIKeyManager(CEREBRAS_API_KEYS)
    return _key_manager
