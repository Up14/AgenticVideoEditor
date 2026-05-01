"""
Core logic for downloading YouTube captions using yt-dlp.

- 'en' means manual English subtitles, with a fallback to auto-generated captions.
- Regional variants are allowed (en-US, en-GB, en-IN, etc.).
- Auto-translated English (hi → en, etc.) supported via cookies.txt.
"""

import os
import tempfile
import shutil
import time
from typing import Dict, Optional, List, Any
from dataclasses import dataclass

import yt_dlp

from utils import (
    parse_vtt_to_text,
    parse_srt_to_text,
    detect_format,
    format_captions_for_display
)
from post_processor import srt_fixPP
from caption_processor import process_captions


@dataclass
class CaptionResult:
    success: bool
    caption_data: List[Dict[str, Any]]
    caption_text: str
    source: Optional[str] = None
    language: Optional[str] = None
    available_languages: Optional[List[str]] = None
    file_path: Optional[str] = None
    error_message: Optional[str] = None


class CaptionDownloader:
    def __init__(self):
        self.temp_dir = tempfile.mkdtemp()

    # --------------------------------------------------
    # Debug helper
    # --------------------------------------------------
    def _debug(self, msg: str):
        print(f"[CaptionDownloader DEBUG] {msg}")

    # --------------------------------------------------
    # Helpers
    # --------------------------------------------------
    def _select_best_track(self, tracks: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not tracks:
            return None
        for ext in ("vtt", "srt"):
            for track in tracks:
                if track.get("ext") == ext:
                    return track
        return tracks[0]

    def _extract_language_list(self, metadata: Dict) -> List[str]:
        languages = set()
        if metadata.get("subtitles"):
            languages.update(metadata["subtitles"].keys())
        if metadata.get("automatic_captions"):
            languages.update(metadata["automatic_captions"].keys())
        return sorted(languages)

    def _pick_manual_english(self, subtitles: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        english_langs = sorted(
            lang for lang in subtitles.keys()
            if lang.lower() == "en" or lang.lower().startswith("en-")
        )

        self._debug(f"manual English candidates: {english_langs}")

        for lang in english_langs:
            track = self._select_best_track(subtitles.get(lang, []))
            if track and track.get("url"):
                return {
                    "url": track["url"],
                    "ext": track.get("ext", "vtt"),
                    "source": "manual",
                    "language": lang
                }
        return None

    def _pick_auto_english(self, autocaps: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        english_langs = sorted(
            lang for lang in autocaps.keys()
            if lang.lower() == "en" or lang.lower().startswith("en-")
        )

        self._debug(f"auto English candidates: {english_langs}")

        for lang in english_langs:
            track = self._select_best_track(autocaps.get(lang, []))
            if track and track.get("url"):
                return {
                    "url": track["url"],
                    "ext": track.get("ext", "vtt"),
                    "source": "auto",
                    "language": lang
                }
        return None

    def _pick_translated_english(self, auto_caps: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._debug(f"checking auto-translated English in: {list(auto_caps.keys())}")

        translated_langs = sorted(
            lang for lang in auto_caps.keys()
            if lang.lower().endswith("-en")
        )

        self._debug(f"translated English candidates: {translated_langs}")

        for lang in translated_langs:
            tracks = auto_caps.get(lang, [])
            self._debug(f"{lang} track formats: {[t.get('ext') for t in tracks]}")

            if not tracks:
                continue

            vtt_tracks = [t for t in tracks if t.get("ext") == "vtt"]
            track = vtt_tracks[0] if vtt_tracks else self._select_best_track(tracks)

            if track and track.get("url"):
                return {
                    "url": track["url"],
                    "ext": track.get("ext", "vtt"),
                    "source": "auto-translated",
                    "language": "en",
                    "translated_from": lang.split("-")[0]
                }

        return None

    # --------------------------------------------------
    # Caption track selection
    # --------------------------------------------------
    def _find_caption_track(self, metadata: Dict, requested_lang: str) -> Optional[Dict[str, Any]]:
        subtitles = metadata.get("subtitles", {})
        auto_caps = metadata.get("automatic_captions", {})

        if requested_lang == "en":
            manual_en = self._pick_manual_english(subtitles)
            if manual_en:
                return manual_en

            auto_en = self._pick_auto_english(auto_caps)
            if auto_en:
                return auto_en

            translated_en = self._pick_translated_english(auto_caps)
            if translated_en:
                return translated_en

            return None

        if requested_lang in subtitles:
            track = self._select_best_track(subtitles.get(requested_lang, []))
            if track and track.get("url"):
                return {
                    "url": track["url"],
                    "ext": track.get("ext", "vtt"),
                    "source": "manual",
                    "language": requested_lang
                }

        if requested_lang in auto_caps:
            track = self._select_best_track(auto_caps.get(requested_lang, []))
            if track and track.get("url"):
                return {
                    "url": track["url"],
                    "ext": track.get("ext", "vtt"),
                    "source": "auto",
                    "language": requested_lang
                }

        return None

    # --------------------------------------------------
    # Download + parse
    # --------------------------------------------------
    def _download_caption_file(self, url: str, ext: str, ydl: yt_dlp.YoutubeDL, post_process: bool) -> Optional[str]:
        try:
            self._debug(f"downloading caption: ext={ext}, post_process={post_process}")

            with tempfile.NamedTemporaryFile(
                mode="w+b",
                suffix=f".{ext}",
                delete=False,
                dir=self.temp_dir
            ) as temp_f:
                response = ydl.urlopen(url)
                shutil.copyfileobj(response, temp_f)

            self._debug(
                f"downloaded to {temp_f.name}, "
                f"size={os.path.getsize(temp_f.name)} bytes"
            )

            if post_process:
                self._debug("running subtitle post-processor")
                info = {
                    'filepath': temp_f.name,
                    'requested_subtitles': {
                        'en': {
                            'ext': ext,
                            'data': open(temp_f.name, 'r', encoding='utf-8', errors='replace').read()
                        }
                    }
                }
                postprocessor = srt_fixPP(ydl)
                files_to_delete, info = postprocessor.run(info)
                for f in files_to_delete:
                    os.remove(f)

            return temp_f.name

        except Exception as e:
            self._debug(f"download failed: {e}")
            return None

    def _parse_caption_file(self, file_path: str) -> List[Dict[str, Any]]:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        fmt = detect_format(content)
        self._debug(f"detected caption format: {fmt}")

        return parse_srt_to_text(content) if fmt == "srt" else parse_vtt_to_text(content)

    # --------------------------------------------------
    # Public API
    # --------------------------------------------------
    def download_captions(self, url: str, lang: str = "en") -> CaptionResult:
        try:
            with yt_dlp.YoutubeDL({
                "quiet": True,
                "no_warnings": True,
                "skip_download": True,
                "cookiefile": r"C:\Users\UPANSHU\Downloads\cookies.txt",
                "http_headers": {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept-Language": "en-US,en;q=0.9",
                },
            }) as ydl:

                metadata = ydl.extract_info(url, download=False)

                caption_track = self._find_caption_track(metadata, lang)
                if not caption_track:
                    return CaptionResult(False, [], "", error_message="Captions not available.")

                post_process = caption_track["source"] in ("auto", "auto-translated")


                file_path = self._download_caption_file(
                    caption_track["url"],
                    caption_track["ext"],
                    ydl,
                    post_process
                )

                captions = self._parse_caption_file(file_path)

                # 🔥 ADD THIS BLOCK EXACTLY HERE
                if caption_track["source"] in ("auto", "auto-translated"):
                    processed = process_captions({
                        "source": caption_track["source"],
                        "language": caption_track["language"],
                        "captions": captions
                    })
                    captions = processed["captions"]


                return CaptionResult(
                    success=True,
                    caption_data=captions,
                    caption_text=format_captions_for_display(captions),
                    source=caption_track["source"],
                    language=caption_track["language"],
                    file_path=file_path,
                )

        except Exception as e:
            return CaptionResult(False, [], "", error_message=str(e))

    def cleanup(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir, ignore_errors=True)
