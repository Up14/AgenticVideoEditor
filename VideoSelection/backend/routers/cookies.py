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
