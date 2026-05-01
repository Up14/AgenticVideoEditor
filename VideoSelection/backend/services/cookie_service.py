"""
Cookie service — handles "Safe Extraction" of cookies from running browsers.

To bypass the "database is locked" error on Windows:
1. Locate the browser's profile (e.g., Chrome 'Default' profile).
2. Create a temporary 'shadow' directory.
3. Copy the 'Cookies' and 'Local State' files to the shadow directory.
4. Tell yt-dlp to use this shadow directory.
"""

import os
import shutil
import tempfile
import logging
from typing import Dict, Any, Optional
import yt_dlp

logger = logging.getLogger(__name__)

def get_browser_user_data_path(browser: str) -> Optional[str]:
    """Returns the base path for a browser's User Data on Windows."""
    appdata = os.getenv("LOCALAPPDATA")
    if not appdata:
        return None
    
    paths = {
        "chrome": os.path.join(appdata, "Google", "Chrome", "User Data"),
        "edge": os.path.join(appdata, "Microsoft", "Edge", "User Data"),
        "brave": os.path.join(appdata, "BraveSoftware", "Brave-Browser", "User Data"),
        "opera": os.path.join(os.getenv("APPDATA", ""), "Opera Software", "Opera Stable"),
    }
    return paths.get(browser.lower())

# Path for the persistent cached cookies
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
COOKIE_CACHE_FILE = os.path.join(MEDIA_DIR, "videdi_cookies.txt")
COOKIES_FILE = os.path.join(MEDIA_DIR, "cookies.txt")


class CookieExtractionError(Exception):
    pass


def _detect_browser() -> tuple[str, str] | None:
    """Returns (yt_dlp_browser_name, display_name) for the first available browser."""
    import sys
    candidates = []
    if sys.platform == "win32":
        candidates = [("chrome", "Chrome"), ("edge", "Edge"), ("brave", "Brave")]
    else:
        # Linux / macOS — check profile dirs
        home = os.path.expanduser("~")
        linux_browsers = [
            ("chromium", "Chromium", os.path.join(home, ".config", "chromium")),
            ("chrome", "Chrome", os.path.join(home, ".config", "google-chrome")),
            ("firefox", "Firefox", os.path.join(home, ".mozilla", "firefox")),
            ("brave", "Brave", os.path.join(home, ".config", "BraveSoftware", "Brave-Browser")),
        ]
        for yt_name, display, profile_path in linux_browsers:
            if os.path.exists(profile_path):
                candidates.append((yt_name, display))

    return candidates[0] if candidates else None


def extract_chrome_cookies() -> str:
    """Extract YouTube cookies from the best available browser and save to media/cookies.txt."""
    browser = _detect_browser()
    if browser is None:
        raise CookieExtractionError(
            "No supported browser found. Install Chromium and log into YouTube, then try again."
        )

    yt_name, display_name = browser
    try:
        ydl_opts = {
            "cookiesfrombrowser": (yt_name,),
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
    except Exception as e:
        raise CookieExtractionError(
            f"Could not read {display_name} cookies. Make sure you're logged into YouTube in {display_name}, then try again."
        )

    if not os.path.exists(COOKIES_FILE) or os.path.getsize(COOKIES_FILE) == 0:
        raise CookieExtractionError(
            f"No cookies found in {display_name}. Open {display_name}, log into YouTube, then try again."
        )

    return COOKIES_FILE

def robust_copy(src: str, dst: str) -> bool:
    """Attempts a robust copy on Windows, handles locks better than shutil."""
    if not os.path.exists(src):
        return False
    
    # 1. Try standard copy first
    try:
        shutil.copy2(src, dst)
        return True
    except (PermissionError, OSError):
        pass

    # 2. Try robocopy (Windows specific)
    src_dir = os.path.dirname(src)
    src_file = os.path.basename(src)
    dst_dir = os.path.dirname(dst)
    
    # /R:0 = zero retries, /W:0 = zero wait, /NP = no progress
    cmd = f'robocopy "{src_dir}" "{dst_dir}" "{src_file}" /R:0 /W:0 /NP >nul 2>&1'
    result = os.system(cmd)
    
    # Robocopy return codes 0-3 are success states
    return os.path.exists(dst)

# -- Re-implementing create_shadow_profile with robust_copy --

def create_shadow_profile(browser: str) -> Optional[str]:
    """
    Creates a persistent shadow profile to cache cookies.
    If the database is locked, it returns the existing shadow if it exists.
    """
    base_path = get_browser_user_data_path(browser)
    if not base_path or not os.path.exists(base_path):
        return None

    shadow_dir = os.path.join(MEDIA_DIR, f"shadow_{browser}")
    os.makedirs(shadow_dir, exist_ok=True)

    try:
        profile_rel_path = "Default"
        profile_path = os.path.join(base_path, profile_rel_path)
        if not os.path.exists(profile_path):
            profile_path = base_path
            profile_rel_path = ""

        # 1. Copy Local State
        local_state_src = os.path.join(base_path, "Local State")
        if os.path.exists(local_state_src):
            robust_copy(local_state_src, os.path.join(shadow_dir, "Local State"))

        # 2. Copy Cookies
        target_profile_dir = os.path.join(shadow_dir, profile_rel_path)
        os.makedirs(target_profile_dir, exist_ok=True)
        
        cookies_src = os.path.join(profile_path, "Network", "Cookies")
        if not os.path.exists(cookies_src):
            cookies_src = os.path.join(profile_path, "Cookies")
            
        if os.path.exists(cookies_src):
            dest = os.path.join(target_profile_dir, "Cookies")
            success = robust_copy(cookies_src, dest)
            
            if success:
                logger.info(f"Successfully updated shadow cookies for {browser}")
            elif os.path.exists(dest):
                logger.info(f"Update failed (locked), using existing cached cookies for {browser}")
            else:
                logger.error(f"Failed to extract cookies and no cache exists for {browser}")
                return None
                
            return shadow_dir
        return None

    except Exception as e:
        logger.error(f"Shadow profile error: {e}")
        return None

def get_smart_cookie_opts() -> Dict[str, Any]:
    """Returns yt-dlp cookie options with caching support."""
    # 1. Check if user set a manual permanent path
    manual_path = os.getenv("YOUTUBE_COOKIES_PATH")
    if manual_path and os.path.exists(manual_path):
        return {"cookiefile": manual_path}

    # 2. Try SMART extraction (Shadow Cache)
    browser = os.getenv("SMART_COOKIE_BROWSER")
    if browser:
        shadow_path = create_shadow_profile(browser)
        if shadow_path:
            return {"cookiesfrombrowser": (browser, shadow_path)}
            
    # 3. Fallback to basic browser extraction (might lock)
    cookie_browser = os.getenv("YOUTUBE_COOKIES_BROWSER")
    if cookie_browser:
        return {"cookiesfrombrowser": (cookie_browser,)}

    # 4. Fallback: use previously extracted cookies file
    if os.path.exists(COOKIES_FILE):
        return {"cookiefile": COOKIES_FILE}

    return {}

def cleanup_shadow_profile(ydl_opts: Dict[str, Any]):
    """
    Modified: We no longer delete the shadow profile folder 
    automatically so we can reuse it next time if the browser is locked.
    """
    pass
