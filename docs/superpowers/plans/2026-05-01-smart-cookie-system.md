# Smart Cookie System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a cookie consent modal on first app load that blocks the app, then auto-extracts YouTube cookies from Chrome on accept and uses them for all future yt-dlp downloads.

**Architecture:** A new `POST /api/cookies/extract` endpoint triggers yt-dlp's Chrome cookie extraction and saves the result to `media/cookies.txt`. `get_smart_cookie_opts()` in `cookie_service.py` gains a fallback to use that file when no env vars are set. The frontend gates the entire app behind a `CookieConsentModal` component whose decision is persisted in `localStorage`.

**Tech Stack:** FastAPI, yt-dlp (cookie extraction), React 19 + TypeScript, localStorage

---

## File Map

| Action | File |
|---|---|
| Modify | `VideoSelection/backend/services/cookie_service.py` |
| Create | `VideoSelection/backend/routers/cookies.py` |
| Modify | `VideoSelection/backend/main.py` |
| Modify | `VideoSelection/frontend/src/api/client.ts` |
| Create | `VideoSelection/frontend/src/components/CookieConsentModal.tsx` |
| Create | `VideoSelection/frontend/src/components/CookieConsentModal.css` |
| Modify | `VideoSelection/frontend/src/App.tsx` |
| Create | `VideoSelection/backend/tests/test_cookie_service.py` |

---

## Task 1: Update `cookie_service.py` — add extraction function + fallback

**Files:**
- Modify: `VideoSelection/backend/services/cookie_service.py`
- Create: `VideoSelection/backend/tests/test_cookie_service.py`

- [ ] **Step 1: Write the failing tests**

Create `VideoSelection/backend/tests/__init__.py` (empty), then create `VideoSelection/backend/tests/test_cookie_service.py`:

```python
import os
import pytest
from unittest.mock import patch, MagicMock

# Run from VideoSelection/backend/
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from services.cookie_service import (
    extract_chrome_cookies,
    CookieExtractionError,
    COOKIES_FILE,
    get_smart_cookie_opts,
)


def test_cookies_file_constant_points_to_media_dir():
    assert COOKIES_FILE.endswith("cookies.txt")
    assert "media" in COOKIES_FILE


def test_extract_chrome_cookies_raises_on_ydl_error(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "services.cookie_service.COOKIES_FILE",
        str(tmp_path / "cookies.txt"),
    )
    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(side_effect=Exception("database is locked"))
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_ydl_cls.return_value = mock_ctx

        with pytest.raises(CookieExtractionError):
            extract_chrome_cookies()


def test_extract_chrome_cookies_raises_when_file_not_created(tmp_path, monkeypatch):
    fake_path = str(tmp_path / "cookies.txt")
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", fake_path)

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.extract_info = MagicMock(return_value={})
        mock_ydl_cls.return_value = mock_instance

        with pytest.raises(CookieExtractionError):
            extract_chrome_cookies()


def test_extract_chrome_cookies_returns_path_on_success(tmp_path, monkeypatch):
    fake_path = str(tmp_path / "cookies.txt")
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", fake_path)

    def fake_enter(self):
        # Simulate yt-dlp writing the cookies file on context exit
        with open(fake_path, "w") as f:
            f.write("# Netscape HTTP Cookie File\nyoutube.com\n")
        return self

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_instance = MagicMock()
        mock_instance.__enter__ = fake_enter.__get__(mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        mock_instance.extract_info = MagicMock(return_value={})
        mock_ydl_cls.return_value = mock_instance

        result = extract_chrome_cookies()
        assert result == fake_path


def test_get_smart_cookie_opts_falls_back_to_cookies_file(tmp_path, monkeypatch):
    fake_path = str(tmp_path / "cookies.txt")
    with open(fake_path, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", fake_path)
    monkeypatch.delenv("YOUTUBE_COOKIES_PATH", raising=False)
    monkeypatch.delenv("SMART_COOKIE_BROWSER", raising=False)
    monkeypatch.delenv("YOUTUBE_COOKIES_BROWSER", raising=False)

    opts = get_smart_cookie_opts()
    assert opts == {"cookiefile": fake_path}


def test_get_smart_cookie_opts_no_fallback_when_file_missing(monkeypatch):
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", "/nonexistent/cookies.txt")
    monkeypatch.delenv("YOUTUBE_COOKIES_PATH", raising=False)
    monkeypatch.delenv("SMART_COOKIE_BROWSER", raising=False)
    monkeypatch.delenv("YOUTUBE_COOKIES_BROWSER", raising=False)

    opts = get_smart_cookie_opts()
    assert opts == {}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd VideoSelection/backend && python -m pytest tests/test_cookie_service.py -v
```

Expected: `ImportError` — `CookieExtractionError`, `extract_chrome_cookies`, `COOKIES_FILE` not defined yet.

- [ ] **Step 3: Add `COOKIES_FILE`, `CookieExtractionError`, `extract_chrome_cookies()` to `cookie_service.py`**

Add these at the top of `VideoSelection/backend/services/cookie_service.py`, after the existing `MEDIA_DIR` / `COOKIE_CACHE_FILE` block:

```python
import yt_dlp

COOKIES_FILE = os.path.join(MEDIA_DIR, "cookies.txt")


class CookieExtractionError(Exception):
    pass


def extract_chrome_cookies() -> str:
    """Extract YouTube cookies from Chrome and save to media/cookies.txt."""
    try:
        ydl_opts = {
            "cookiesfrombrowser": ("chrome",),
            "cookiefile": COOKIES_FILE,
            "quiet": True,
            "no_warnings": True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.extract_info(
                    "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
                    download=False,
                )
            except Exception:
                pass  # Video errors are irrelevant; we only need the cookie file written
    except Exception:
        raise CookieExtractionError("Please close Chrome and try again")

    if not os.path.exists(COOKIES_FILE) or os.path.getsize(COOKIES_FILE) == 0:
        raise CookieExtractionError("Please close Chrome and try again")

    return COOKIES_FILE
```

- [ ] **Step 4: Add `COOKIES_FILE` fallback to the end of `get_smart_cookie_opts()`**

In `get_smart_cookie_opts()`, replace the final `return {}` line with:

```python
    # 4. Fallback: use previously extracted cookies file
    if os.path.exists(COOKIES_FILE):
        return {"cookiefile": COOKIES_FILE}

    return {}
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
cd VideoSelection/backend && python -m pytest tests/test_cookie_service.py -v
```

Expected: all 6 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add VideoSelection/backend/services/cookie_service.py \
        VideoSelection/backend/tests/__init__.py \
        VideoSelection/backend/tests/test_cookie_service.py
git commit -m "feat: add extract_chrome_cookies() and cookies.txt fallback to cookie_service"
```

---

## Task 2: Create `routers/cookies.py`

**Files:**
- Create: `VideoSelection/backend/routers/cookies.py`

- [ ] **Step 1: Write the failing test**

Add to `VideoSelection/backend/tests/test_cookie_service.py` (append at the bottom):

```python
# ── Router tests ──
from fastapi.testclient import TestClient


def test_cookies_status_returns_false_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", str(tmp_path / "cookies.txt"))
    # Import after monkeypatching so the router picks up the new path
    import importlib, routers.cookies as rc
    importlib.reload(rc)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(rc.router)
    client = TestClient(app)

    response = client.get("/api/cookies/status")
    assert response.status_code == 200
    assert response.json() == {"available": False}


def test_cookies_extract_returns_error_on_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", str(tmp_path / "cookies.txt"))
    import importlib, routers.cookies as rc
    importlib.reload(rc)
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(rc.router)
    client = TestClient(app)

    with patch("routers.cookies.extract_chrome_cookies", side_effect=CookieExtractionError("Please close Chrome and try again")):
        response = client.post("/api/cookies/extract")
    assert response.status_code == 200
    assert response.json()["success"] is False
    assert "Chrome" in response.json()["error"]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd VideoSelection/backend && python -m pytest tests/test_cookie_service.py::test_cookies_status_returns_false_when_no_file tests/test_cookie_service.py::test_cookies_extract_returns_error_on_failure -v
```

Expected: `ModuleNotFoundError` — `routers.cookies` not found.

- [ ] **Step 3: Create `VideoSelection/backend/routers/cookies.py`**

```python
import os
from fastapi import APIRouter
from pydantic import BaseModel

from services.cookie_service import extract_chrome_cookies, CookieExtractionError, COOKIES_FILE

router = APIRouter(prefix="/api/cookies", tags=["cookies"])


class ExtractResponse(BaseModel):
    success: bool
    error: str | None = None


class StatusResponse(BaseModel):
    available: bool


@router.post("/extract", response_model=ExtractResponse)
async def extract_cookies():
    try:
        extract_chrome_cookies()
        return ExtractResponse(success=True)
    except CookieExtractionError as e:
        return ExtractResponse(success=False, error=str(e))


@router.get("/status", response_model=StatusResponse)
async def cookies_status():
    available = os.path.exists(COOKIES_FILE) and os.path.getsize(COOKIES_FILE) > 0
    return StatusResponse(available=available)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd VideoSelection/backend && python -m pytest tests/test_cookie_service.py -v
```

Expected: all 8 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add VideoSelection/backend/routers/cookies.py \
        VideoSelection/backend/tests/test_cookie_service.py
git commit -m "feat: add /api/cookies/extract and /api/cookies/status endpoints"
```

---

## Task 3: Register cookies router in `main.py`

**Files:**
- Modify: `VideoSelection/backend/main.py`

- [ ] **Step 1: Add the import and router registration**

In `VideoSelection/backend/main.py`, add the import alongside the existing router imports:

```python
from routers.cookies import router as cookies_router
```

Then add the router registration after the existing `app.include_router(clip_selector_router)` line:

```python
app.include_router(cookies_router)
```

- [ ] **Step 2: Verify the server starts**

```bash
cd VideoSelection/backend && uvicorn main:app --port 8000 --reload &
sleep 2 && curl -s http://127.0.0.1:8000/api/cookies/status
```

Expected output: `{"available":false}` (no cookies.txt yet).

Kill the server: `pkill -f "uvicorn main:app"`

- [ ] **Step 3: Commit**

```bash
git add VideoSelection/backend/main.py
git commit -m "feat: register cookies router in FastAPI app"
```

---

## Task 4: Add `extractCookies()` to `client.ts`

**Files:**
- Modify: `VideoSelection/frontend/src/api/client.ts`

- [ ] **Step 1: Add the interface and function**

Append to the end of `VideoSelection/frontend/src/api/client.ts`:

```typescript
export interface CookieExtractResponse {
  success: boolean;
  error?: string;
}

/**
 * POST /api/cookies/extract — Extract YouTube cookies from Chrome.
 */
export async function extractCookies(): Promise<CookieExtractResponse> {
  const res = await fetch(`${API_BASE}/api/cookies/extract`, {
    method: "POST",
  });

  if (!res.ok) {
    return { success: false, error: `HTTP ${res.status}` };
  }

  return res.json();
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd VideoSelection/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add VideoSelection/frontend/src/api/client.ts
git commit -m "feat: add extractCookies() API client function"
```

---

## Task 5: Create `CookieConsentModal.tsx` + `CookieConsentModal.css`

**Files:**
- Create: `VideoSelection/frontend/src/components/CookieConsentModal.tsx`
- Create: `VideoSelection/frontend/src/components/CookieConsentModal.css`

- [ ] **Step 1: Create `CookieConsentModal.css`**

Create `VideoSelection/frontend/src/components/CookieConsentModal.css`:

```css
.cookie-modal__overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.85);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.cookie-modal__box {
  background: #1a1a2e;
  border: 1px solid #2a2a4a;
  border-radius: 12px;
  padding: 40px;
  max-width: 480px;
  width: 90%;
  text-align: center;
  color: #e0e0e0;
}

.cookie-modal__box h2 {
  font-size: 1.5rem;
  margin-bottom: 16px;
  color: #ffffff;
}

.cookie-modal__box p {
  font-size: 0.95rem;
  line-height: 1.6;
  color: #a0a0b0;
  margin-bottom: 24px;
}

.cookie-modal__actions {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.cookie-modal__btn {
  padding: 12px 24px;
  border-radius: 8px;
  font-size: 0.95rem;
  font-weight: 600;
  cursor: pointer;
  border: none;
  transition: opacity 0.2s;
}

.cookie-modal__btn:hover {
  opacity: 0.85;
}

.cookie-modal__btn--accept {
  background: #4f46e5;
  color: #ffffff;
}

.cookie-modal__btn--decline {
  background: transparent;
  color: #666680;
  border: 1px solid #2a2a4a;
}

.cookie-modal__loading {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  color: #a0a0b0;
}

.cookie-modal__spinner {
  width: 32px;
  height: 32px;
  border: 3px solid #2a2a4a;
  border-top-color: #4f46e5;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

.cookie-modal__error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.cookie-modal__error p {
  color: #f87171;
  margin-bottom: 0;
}

.cookie-modal__blocked {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: #0f0f1a;
  color: #a0a0b0;
  gap: 16px;
  text-align: center;
  padding: 40px;
}

.cookie-modal__blocked h2 {
  color: #ffffff;
  font-size: 1.4rem;
}

.cookie-modal__blocked p {
  max-width: 400px;
  line-height: 1.6;
}
```

- [ ] **Step 2: Create `CookieConsentModal.tsx`**

Create `VideoSelection/frontend/src/components/CookieConsentModal.tsx`:

```tsx
import { useState } from "react";
import { extractCookies } from "../api/client";
import "./CookieConsentModal.css";

type ModalState = "idle" | "loading" | "error";

interface Props {
  onAccepted: () => void;
  onDeclined: () => void;
}

export default function CookieConsentModal({ onAccepted, onDeclined }: Props) {
  const [state, setState] = useState<ModalState>("idle");
  const [errorMsg, setErrorMsg] = useState("");

  async function handleAccept() {
    setState("loading");
    const result = await extractCookies();
    if (result.success) {
      onAccepted();
    } else {
      setErrorMsg(result.error ?? "Please close Chrome and try again.");
      setState("error");
    }
  }

  return (
    <div className="cookie-modal__overlay">
      <div className="cookie-modal__box">
        <h2>Cookie Access Required</h2>
        <p>
          This app needs access to your YouTube cookies to download videos.
          Your cookies are stored locally and never sent to any external server.
        </p>

        {state === "idle" && (
          <div className="cookie-modal__actions">
            <button
              className="cookie-modal__btn cookie-modal__btn--accept"
              onClick={handleAccept}
            >
              Accept All Cookies
            </button>
            <button
              className="cookie-modal__btn cookie-modal__btn--decline"
              onClick={onDeclined}
            >
              Decline
            </button>
          </div>
        )}

        {state === "loading" && (
          <div className="cookie-modal__loading">
            <div className="cookie-modal__spinner" />
            <p>Extracting cookies from Chrome...</p>
          </div>
        )}

        {state === "error" && (
          <div className="cookie-modal__error">
            <p>{errorMsg}</p>
            <button
              className="cookie-modal__btn cookie-modal__btn--accept"
              onClick={handleAccept}
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd VideoSelection/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add VideoSelection/frontend/src/components/CookieConsentModal.tsx \
        VideoSelection/frontend/src/components/CookieConsentModal.css
git commit -m "feat: add CookieConsentModal component"
```

---

## Task 6: Gate `App.tsx` behind cookie consent

**Files:**
- Modify: `VideoSelection/frontend/src/App.tsx`

- [ ] **Step 1: Add consent state and logic to `App.tsx`**

At the top of `App.tsx`, add the import alongside existing component imports:

```tsx
import CookieConsentModal from "./components/CookieConsentModal";
```

Inside the `App` component function, add this state block right after the existing state declarations (after the `const [isExporting, setIsExporting]` line):

```tsx
// ── Cookie Consent ──
const [consentStatus, setConsentStatus] = useState<"unknown" | "accepted" | "declined">(() => {
  const stored = localStorage.getItem("cookie_consent");
  if (stored === "accepted") return "accepted";
  if (stored === "declined") return "declined";
  return "unknown";
});

function handleCookieAccepted() {
  localStorage.setItem("cookie_consent", "accepted");
  setConsentStatus("accepted");
}

function handleCookieDeclined() {
  localStorage.setItem("cookie_consent", "declined");
  setConsentStatus("declined");
}

function handleReopenConsent() {
  localStorage.removeItem("cookie_consent");
  setConsentStatus("unknown");
}
```

- [ ] **Step 2: Add consent gate to the render output**

Place these two early-return blocks directly BEFORE the existing `return (` statement in `App.tsx` (not inside it):

```tsx
if (consentStatus === "unknown") {
  return (
    <CookieConsentModal
      onAccepted={handleCookieAccepted}
      onDeclined={handleCookieDeclined}
    />
  );
}

if (consentStatus === "declined") {
  return (
    <div className="cookie-modal__blocked">
      <h2>Cookie Access Required</h2>
      <p>
        This app requires access to your YouTube cookies to function.
        Please accept cookies to continue.
      </p>
      <button
        className="cookie-modal__btn cookie-modal__btn--accept"
        onClick={handleReopenConsent}
        style={{ padding: "12px 24px", borderRadius: "8px", background: "#4f46e5", color: "#fff", border: "none", cursor: "pointer", fontWeight: 600 }}
      >
        Review Cookie Settings
      </button>
    </div>
  );
}
```

- [ ] **Step 3: Import the CSS in `App.tsx`** (so blocked screen styles are available)

Add this import near the top of `App.tsx` alongside the existing CSS import:

```tsx
import "./components/CookieConsentModal.css";
```

- [ ] **Step 4: Verify TypeScript compiles**

```bash
cd VideoSelection/frontend && npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 5: Manual smoke test**

Start backend and frontend:

```bash
# Terminal 1
cd VideoSelection/backend && uvicorn main:app --port 8000 --reload

# Terminal 2
cd VideoSelection/frontend && npm run dev
```

Open `http://localhost:5173` in browser.

Verify:
1. Cookie modal appears immediately (blocking the app)
2. Click "Decline" → blocked screen appears with "Review Cookie Settings" button
3. Click "Review Cookie Settings" → modal re-appears
4. Click "Accept All Cookies" → spinner appears → either succeeds (Chrome found) or shows error "Please close Chrome and try again"
5. On success → modal dismissed → full app visible
6. Refresh page → no modal (localStorage remembered)
7. Open DevTools → Application → Local Storage → delete `cookie_consent` → refresh → modal re-appears

- [ ] **Step 6: Commit**

```bash
git add VideoSelection/frontend/src/App.tsx
git commit -m "feat: gate app behind cookie consent modal"
```

---

## Task 7: Verify end-to-end cookie flow

- [ ] **Step 1: Run all backend tests**

```bash
cd VideoSelection/backend && python -m pytest tests/ -v
```

Expected: all 8 tests PASS.

- [ ] **Step 2: Verify cookies.txt is used by downloader**

With the server running and `media/cookies.txt` present (after accepting in UI):

```bash
curl -s http://127.0.0.1:8000/api/cookies/status
```

Expected: `{"available":true}`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: smart cookie system complete — modal, extraction, yt-dlp fallback"
```
