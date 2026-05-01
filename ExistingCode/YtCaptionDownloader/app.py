"""
YouTube Caption Downloader - Streamlit App
Strict English Mode:
- English = regional English only (en-XX)
- No auto-generated base 'en'
"""

import streamlit as st
from caption_downloader import CaptionDownloader
from utils import (
    convert_to_srt,
    convert_to_vtt,
    convert_to_txt,
    convert_to_json
)

# --------------------------------------------------
# Page configuration
# --------------------------------------------------
st.set_page_config(
    page_title="YouTube Caption Downloader",
    page_icon="📝",
    layout="centered"
)

# --------------------------------------------------
# Session state initialization
# --------------------------------------------------
if "downloader" not in st.session_state:
    st.session_state.downloader = CaptionDownloader()

if "last_result" not in st.session_state:
    st.session_state.last_result = None

if "last_url" not in st.session_state:
    st.session_state.last_url = ""

if "last_lang" not in st.session_state:
    st.session_state.last_lang = "en"

# --------------------------------------------------
# Language options
# --------------------------------------------------
LANGUAGE_OPTIONS = {
    "Auto-detect": "auto",
    "English (regional only)": "en",
    "Hindi": "hi",
    "Spanish": "es",
    "French": "fr",
    "German": "de",
    "Italian": "it",
    "Portuguese": "pt",
    "Japanese": "ja",
    "Korean": "ko",
    "Chinese": "zh",
    "Russian": "ru",
    "Arabic": "ar",
    "Turkish": "tr",
    "Dutch": "nl",
    "Polish": "pl",
}

# --------------------------------------------------
# UI Header
# --------------------------------------------------
st.title("📝 YouTube Caption Downloader")
st.markdown(
    """
Download captions from YouTube videos.

**English behavior**
- ✔ Uses only regional English captions (`en-GB`, `en-IN`, `en-US`)
- ❌ Auto-generated base `en` captions are ignored
"""
)

# --------------------------------------------------
# Input Section
# --------------------------------------------------
st.header("Video Information")

url = st.text_input(
    "YouTube URL",
    value=st.session_state.last_url,
    placeholder="https://www.youtube.com/watch?v=...",
    help="Enter the full YouTube video URL"
)

lang_display = st.selectbox(
    "Language",
    options=list(LANGUAGE_OPTIONS.keys()),
    index=list(LANGUAGE_OPTIONS.values()).index(st.session_state.last_lang)
    if st.session_state.last_lang in LANGUAGE_OPTIONS.values()
    else 1,
    help="English returns only regional captions (no auto ASR)."
)

lang_code = LANGUAGE_OPTIONS[lang_display]

download_button = st.button(
    "Download Captions",
    type="primary",
    use_container_width=True
)

# --------------------------------------------------
# Download processing
# --------------------------------------------------
if download_button:
    if not url or not url.strip():
        st.error("❌ Please enter a valid YouTube URL.")
    elif "youtube.com" not in url and "youtu.be" not in url:
        st.error("❌ Please enter a valid YouTube URL.")
    else:
        with st.spinner("Downloading captions..."):
            result = st.session_state.downloader.download_captions(
                url.strip(),
                lang_code
            )

            st.session_state.last_result = result
            st.session_state.last_url = url.strip()
            st.session_state.last_lang = lang_code

# --------------------------------------------------
# Display results
# --------------------------------------------------
if st.session_state.last_result:
    result = st.session_state.last_result

    if result.success:
        st.success(
            f"✅ Captions downloaded successfully! "
            f"(Source: {result.source}, Language: {result.language})"
        )

        # Captions display
        st.header("Captions")
        st.text_area(
            "Caption Text",
            value=result.caption_text,
            height=400,
            disabled=True,
            label_visibility="collapsed"
        )

        # Downloads
        st.header("Download")
        st.markdown("Download captions in your preferred format:")

        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.download_button(
                "📄 Download SRT",
                convert_to_srt(result.caption_data),
                file_name=f"captions_{result.language}.srt",
                mime="text/plain",
                use_container_width=True
            )

        with col2:
            st.download_button(
                "📄 Download VTT",
                convert_to_vtt(result.caption_data),
                file_name=f"captions_{result.language}.vtt",
                mime="text/vtt",
                use_container_width=True
            )

        with col3:
            st.download_button(
                "📄 Download TXT",
                convert_to_txt(result.caption_data),
                file_name=f"captions_{result.language}.txt",
                mime="text/plain",
                use_container_width=True
            )

        with col4:
            st.download_button(
                "📄 Download JSON",
                convert_to_json(
                    result.caption_data,
                    result.source,
                    result.language
                ),
                file_name=f"captions_{result.language}.json",
                mime="application/json",
                use_container_width=True
            )

    else:
        st.error(f"❌ {result.error_message}")

        if result.available_languages:
            st.info(
                "💡 Available caption languages:\n\n"
                + ", ".join(result.available_languages)
            )

# --------------------------------------------------
# Footer
# --------------------------------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:gray;'>"
    "Regional English captions only — auto ASR is intentionally disabled."
    "</div>",
    unsafe_allow_html=True
)

# --------------------------------------------------
# Cleanup
# --------------------------------------------------
import atexit
atexit.register(st.session_state.downloader.cleanup)
