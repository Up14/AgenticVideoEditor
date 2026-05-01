# Smart Cookie System — Design Spec
Date: 2026-05-01

## Overview

Show a cookie consent modal on first app load that blocks the app until the user accepts. On accept, the backend auto-extracts YouTube cookies from the user's local Chrome profile and saves them for all future yt-dlp downloads. Consent is remembered in localStorage.

---

## Requirements

- Popup appears once on first load; localStorage remembers the decision
- "Accept All Cookies" triggers backend Chrome cookie extraction
- If extraction fails (Chrome DB locked, profile not found) → show error asking user to close Chrome and retry
- "Decline" → app is blocked with a message and a button to re-open the modal
- Chrome is the only supported browser for extraction
- Extracted cookies saved to `media/cookies.txt` and used by all yt-dlp calls

---

## Architecture

### New Files
| File | Purpose |
|---|---|
| `VideoSelection/backend/routers/cookies.py` | Two endpoints: extract + status |
| `VideoSelection/frontend/src/components/CookieConsentModal.tsx` | Consent modal component |

### Modified Files
| File | Change |
|---|---|
| `VideoSelection/backend/main.py` | Register cookies router |
| `VideoSelection/backend/services/cookie_service.py` | Add `extract_chrome_cookies()` function |
| `VideoSelection/frontend/src/App.tsx` | Gate app behind consent check |
| `VideoSelection/frontend/src/api/client.ts` | Add `extractCookies()` API call |

---

## Backend

### `routers/cookies.py`

**`POST /api/cookies/extract`**
- Calls `cookie_service.extract_chrome_cookies()`
- On success: returns `{ "success": true }`
- On failure: returns `{ "success": false, "error": "Please close Chrome and try again" }`

**`GET /api/cookies/status`**
- Checks if `media/cookies.txt` exists
- Returns `{ "available": true }` or `{ "available": false }`

### `services/cookie_service.py`

Add `extract_chrome_cookies() -> str`:
- Targets Chrome profile only
- Uses existing shadow-profile copy logic (temp DB copy to bypass lock)
- Extracts YouTube cookies from copied DB
- Saves result to `media/cookies.txt`
- Raises `CookieExtractionError` with a clear message if DB is locked or profile not found

### `downloader.py` + `caption_service.py`

Both files already check `YOUTUBE_COOKIES_PATH` env var for a cookies path. Add a fallback: if `YOUTUBE_COOKIES_PATH` is not set, check if `media/cookies.txt` exists and use it. This means cookies take effect immediately after extraction — no server restart required.

---

## Frontend

### `CookieConsentModal.tsx`

Full-screen overlay. Three internal states:

| State | UI |
|---|---|
| `idle` | Consent banner with "Accept All Cookies" and "Decline" buttons |
| `loading` | Spinner while `POST /api/cookies/extract` runs |
| `error` | Error message "Please close Chrome and try again" + Retry button |

Props:
- `onAccepted: () => void` — called on successful extraction
- `onDeclined: () => void` — called when user declines

### `App.tsx`

On mount, reads `localStorage.getItem('cookie_consent')`:

| Value | Behaviour |
|---|---|
| `null` | Render `<CookieConsentModal>` as full-screen overlay |
| `"accepted"` | Proceed normally — app fully unlocked |
| `"declined"` | Show blocked screen with "Cookie access required" and re-open button |

On accept success → `localStorage.setItem('cookie_consent', 'accepted')` → dismiss modal  
On decline → `localStorage.setItem('cookie_consent', 'declined')` → show blocked screen

### `client.ts`

Add:
```ts
extractCookies(): Promise<{ success: boolean; error?: string }>
  // POST /api/cookies/extract
```

---

## Data Flow

```
App loads
  → App.tsx checks localStorage('cookie_consent')
  → null → CookieConsentModal renders (app blocked)

User clicks "Accept All Cookies"
  → Modal: loading state
  → POST /api/cookies/extract
  → cookie_service.extract_chrome_cookies()
      → locate Chrome profile on disk
      → copy DB to temp path (shadow profile, bypasses lock)
      → extract YouTube cookies → save to media/cookies.txt
  → success  → localStorage = 'accepted' → modal dismissed → app unlocked
  → failure  → modal shows error + Retry button

User clicks "Decline"
  → localStorage = 'declined'
  → App shows: "Cookie access is required to use this app" + re-open button

All future yt-dlp calls
  → --cookies media/cookies.txt passed automatically
```

---

## Error Handling

| Scenario | Behaviour |
|---|---|
| Chrome DB locked (Chrome is open) | Error state: "Please close Chrome and try again" + Retry |
| Chrome profile not found | Error state: same message |
| `media/cookies.txt` missing at download time | yt-dlp proceeds without cookies (may fail for restricted videos) |
| User clears localStorage | Modal re-appears on next load; re-extraction re-creates cookies.txt |
