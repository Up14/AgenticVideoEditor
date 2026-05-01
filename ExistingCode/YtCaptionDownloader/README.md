# YouTube Caption Downloader

A minimal Streamlit web application to download captions from YouTube videos. Supports both manual (uploaded) and auto-generated captions.

## Features

- Download captions from YouTube videos
- Support for multiple languages (with auto-detect option)
- Prefers manual captions over auto-generated ones
- Multiple download formats: SRT, VTT, TXT, JSON
- Displays captions with timestamps in a readable format
- User-friendly error messages

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

## Usage

1. **Run the Streamlit app:**
   ```bash
   streamlit run app.py
   ```

2. **Open your browser** to the URL shown (typically `http://localhost:8501`)

3. **Enter a YouTube URL** and select a language

4. **Click "Download Captions"** to fetch and display the captions

5. **Download** in your preferred format (SRT, VTT, TXT, or JSON)

## How It Works

1. The app uses `yt-dlp` to probe the video for available caption tracks
2. Checks for manual (uploaded) captions first, then falls back to auto-generated captions
3. Downloads the caption file and parses it into a structured format
4. Displays captions with timestamps and provides download options

## Requirements

- Python 3.7 or higher
- `streamlit` - Web framework
- `yt-dlp` - YouTube content downloader
- `webvtt-py` - VTT file parsing (optional, manual parsing also available)

## Limitations

- Captions are only available if YouTube exposes them for the video
- Some videos may have captions disabled or restricted
- Auto-generated captions may not be available for all videos
- If captions are not available, the app will show an error message (no fallback transcription)

## Error Messages

The app provides friendly error messages for common scenarios:
- Invalid YouTube URL
- Video is private, removed, or restricted
- No captions available for the video
- Captions not available in the selected language (with list of available languages)

## Project Structure

```
Transcriptor/
├── app.py                 # Main Streamlit application
├── caption_downloader.py  # Core logic for downloading/processing captions
├── utils.py               # Format conversion utilities
├── requirements.txt       # Python dependencies
└── README.md              # This file
```

## Future Enhancements

The code is structured to easily add:
- STT (Speech-to-Text) fallback when captions aren't available
- Batch processing for multiple URLs
- Progress indicators for longer operations

## License

This project is provided as-is for educational and personal use.
