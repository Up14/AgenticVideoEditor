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

    with patch("yt_dlp.YoutubeDL") as mock_ydl_cls:
        mock_instance = MagicMock()

        def fake_enter():
            with open(fake_path, "w") as f:
                f.write("# Netscape HTTP Cookie File\nyoutube.com\n")
            return mock_instance

        mock_instance.__enter__ = MagicMock(side_effect=lambda: fake_enter())
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


# ── Router tests ──
from fastapi.testclient import TestClient


def test_cookies_status_returns_false_when_no_file(tmp_path, monkeypatch):
    monkeypatch.setattr("services.cookie_service.COOKIES_FILE", str(tmp_path / "cookies.txt"))
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
