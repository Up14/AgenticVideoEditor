
import streamlit as st
import subprocess
import shutil
import os
import gc

def check_dependencies():
    """Check for required command-line tools and provide user-friendly errors."""
    if not shutil.which("python"):
        st.error("FATAL: `python` is not installed or not in the PATH. This app cannot run.")
        st.stop()
        
    if not shutil.which("ffmpeg"):
        st.error("ERROR: `ffmpeg` is not found in the environment PATH.")
        st.info(
            "FFmpeg is required for merging video and audio. "
            "Please add `pkgs.ffmpeg` to your `.idx/dev.nix` file and reload the environment."
        )
        st.stop()
    return True

def download_video(url, quality, safe_mode=False):
    """
    Downloads a YouTube video using yt-dlp, ensuring compatible audio and overwriting old files.
    """
    if not url:
        st.warning("Please enter a YouTube URL.")
        return

    # --- FIX: Cleanup all potential partial/temp files ---
    base_name = f"downloaded_video_{quality}p"
    output_filename = f"{base_name}.mp4"
    
    # Remove final file if exists
    if os.path.exists(output_filename):
        try:
            os.remove(output_filename)
        except OSError:
            # st.error(f"❌ Could not delete the old file: `{output_filename}`")
            # Instead of failing, we generate a unique name
            import time
            timestamp = int(time.time())
            new_filename = f"{base_name}_{timestamp}.mp4"
            st.warning(f"⚠️ Old file `{output_filename}` is locked. Saving as `{new_filename}` instead.")
            output_filename = new_filename

    # Clean up temp/partial files from previous runs (Best effort)
    for file in os.listdir():
        # Only clean up if we are still targeting the original base name, 
        # or if we want to aggressively clean up related files.
        # Here we just try to clean up the specific targets if possible.
        if file.startswith(base_name) and (file.endswith(".part") or ".f" in file or ".temp" in file):
            try:
                os.remove(file)
            except OSError:
                pass

    st.info(f"Starting download for {quality}p video...")
    
    # --- FIX: Request compatible AAC audio (m4a) and use merge-output-format ---
    cmd = [
        "python", "-m", "yt_dlp",
        "--verbose", # Enable verbose logging for debugging
        "-f", f"bestvideo[height<={quality}]+bestaudio[ext=m4a]/bestvideo+bestaudio",
        "--merge-output-format", "mp4",
        "--postprocessor-args", "merger+ffmpeg:-movflags 0", # Disable faststart to save memory
        "--js-runtimes", "node", # Restore nodejs for JS challenges
        "--no-playlist",
        "--force-overwrites", # Ensure it overwrites
        "--no-part", # Fix [WinError 2] FileNotFoundError by writing directly to file (skipping rename)
        
        # --- MEMORY SAFETY ---
        # Limit chunk size to 10MB to prevent `MemoryError` in Python's http client
        # This keeps the buffer small even for large 1080p videos
        "--http-chunk-size", "10M", 
        
        "-o", output_filename,
        url
    ]

    # --- SAFE MODE: Uses ffmpeg downloader to avoid MemoryError on large files ---
    if safe_mode:
        cmd.extend([
            "--downloader", "ffmpeg", 
            "--downloader-args", "ffmpeg:-nostdin",
        ])

    st.info("Running yt-dlp...")

    # --- FIX: Force garbage collection before subprocess ---
    gc.collect()

    # --- FIX: Redirect output to files to avoid MemoryError ---
    # We will also read from the file tailored to show progress
    
    st.write("Initializing download process...")
    # FIX: Merge stderr into stdout to avoid deadlocks when reading only one pipe
    # independent of which downloader is used (native writes to stdout, ffmpeg to stderr)
    process = subprocess.Popen(
        cmd, 
        stdout=subprocess.PIPE, 
        stderr=subprocess.STDOUT, 
        text=True,
        bufsize=1, # Line buffered
        universal_newlines=True
    )

    progress_placeholder = st.empty()
    log_placeholder = st.empty()
    
    # This regex handles the standard HH:MM:SS format from ffmpeg
    import re
    
    logs = []
    total_duration_sec = None
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while True:
        # Check if process is still running
        retcode = process.poll()
        
        # Read a line from stdout (merged stream)
        line = process.stdout.readline()
        if line:
            logs.append(line)
            if len(logs) > 20: logs.pop(0) # Keep last 20 lines
            
            if len(logs) > 20: logs.pop(0) # Keep last 20 lines
            
            # --- Progress Parsing Logic ---
            
            # 1. Parsing for FFMPEG Downloader (Safe Mode)
            # Duration: 01:26:27.60
            if safe_mode and total_duration_sec is None:
                dur_match = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", line)
                if dur_match:
                    h, m, s = dur_match.groups()
                    total_duration_sec = int(h) * 3600 + int(m) * 60 + float(s)

            # time=00:03:59.49
            if safe_mode:
                time_match = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", line)
                if time_match and total_duration_sec:
                    h, m, s = time_match.groups()
                    current_sec = int(h) * 3600 + int(m) * 60 + float(s)
                    if total_duration_sec > 0:
                        fraction = min(max(current_sec / total_duration_sec, 0.0), 1.0)
                        progress_bar.progress(fraction)
                        status_text.text(f"Safe Mode Progress: {fraction:.1%}")
            
            # 2. Parsing for Native Downloader (Fast Mode)
            # [download]  12.7% of  570.94MiB at   12.90MiB/s ETA 00:38
            if not safe_mode:
                # Look for percentage pattern like "12.7%"
                percent_match = re.search(r"(\d+\.\d+)%", line)
                if percent_match:
                    try:
                        percentage = float(percent_match.group(1))
                        fraction = min(max(percentage / 100.0, 0.0), 1.0)
                        progress_bar.progress(fraction)
                        status_text.text(f"Fast Download Progress: {percentage:.1f}%")
                    except ValueError:
                        pass

            # Update logs only if it's not a noisy progress line or update less frequently
            # (Keeping it simple: always update code block for context)
            if not line.strip().startswith("[download]"): # Reduce UI flickering for native logs
                 log_placeholder.code("".join(logs))
            else:
                 # Still show last logs but maybe throttle calling st.code in a real app
                 # For now, just update text above
                 pass
        
        if retcode is not None and not line:
            break
            
    # Wait for process to close
    process.wait()
    
    if process.returncode == 0:
        st.success(f"Download complete! Saved as `{output_filename}`")
        return output_filename
    else:
        st.error("Download failed. yt-dlp exited with an error.")
        st.subheader("Return Code:")
        st.code(process.returncode)
        
        st.subheader("Last Logs:")
        full_log = "".join(logs) or stderr
        st.code(full_log, language="text")
        
        if "MemoryError" in full_log or process.returncode == 3221225477: # Access Violation / Memory often returns huge neg/pos codes
            st.error("🚨 **Memory Error Detected**")
            st.warning("""
                The "Fast" downloader ran out of RAM. This happens with large videos or high-quality streams.
                
                **Solution:**
                1. Check the **'Safe Mode (Slower)'** box above.
                2. Try downloading again.
                
                Safe Mode uses an external tool (ffmpeg) that handles memory much better, though it may take longer.
            """)
        
        return None



# --- Streamlit App UI ---
st.set_page_config(layout="centered")
st.title("🎬 Robust YouTube Video Downloader")
st.markdown(
    "This app uses `yt-dlp` and `ffmpeg` to download YouTube videos "
    "reliably. It invokes `yt-dlp` as a Python module to prevent environment path issues."
)

if not 'dependencies_checked' in st.session_state:
    check_dependencies()
    st.session_state.dependencies_checked = True

# Initialize session state for the downloaded file
if 'downloaded_file' not in st.session_state:
    st.session_state.downloaded_file = None

url = st.text_input("Enter YouTube Video URL")

if url:
    st.subheader("Select Video Quality")
    
    quality_options = [1080, 720, 480, 360]
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        selected_quality = st.selectbox(
            "Choose maximum quality:",
            options=quality_options,
            format_func=lambda x: f"{x}p"
        )
    
    with col2:
        st.write("") # Spacer
        st.write("")
        safe_mode = st.checkbox("Safe Mode (Slower)", help="Use this if you encounter 'MemoryError' or crashes. It uses ffmpeg for downloading which is more stable but slower.")
    
    if st.button("Download Video"):
        with st.spinner("Downloading and merging..."):
            file_path = download_video(url, selected_quality, safe_mode=safe_mode)
            if file_path:
                st.session_state.downloaded_file = file_path
                st.rerun() # Force rerun to show the download button immediately

# Display Download Button if file exists in session state and on disk
if st.session_state.downloaded_file and os.path.exists(st.session_state.downloaded_file):
    st.success("Ready to download!")
    
    # Option 1: Standard Download Button (May cause memory issues for very large files)
    # We will try the standard button first, but if it fails (or to be safe for 1080p),
    # we can also provide a "Direct Link" which uses the static file server.
    
    # Start Background Server if not running
    if "server_started" not in st.session_state:
        import threading
        import http.server
        import socketserver

        PORT = 9999
        
        def start_server():
            # Serve the current directory (where files are downloaded)
            Handler = http.server.SimpleHTTPRequestHandler
            try:
                with socketserver.TCPServer(("", PORT), Handler) as httpd:
                    print(f"Serving at port {PORT}")
                    httpd.serve_forever()
            except OSError:
                print(f"Port {PORT} already in use. Assuming server is running.")

        # Daemon thread so it dies when main app dies
        thread = threading.Thread(target=start_server, daemon=True)
        thread.start()
        st.session_state.server_started = True

    col_dll_1, col_dll_2 = st.columns(2)
    
    with col_dll_1:
         # Direct Localhost Link (Guaranteed to work if server is up)
         filename = os.path.basename(st.session_state.downloaded_file)
         local_url = f"http://localhost:9999/{filename}"
         
         st.markdown("### ⬇️ Local Direct Download")
         st.success("Use this link for 100% reliable local download.")
         
         st.markdown(
             f'<a href="{local_url}" download="{filename}" target="_blank" style="background-color: #FF4B4B; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; font-weight: bold; display: inline-block;">⬇️ Download Now (Port 9999)</a>',
             unsafe_allow_html=True
         )

    with col_dll_2:
        # Option 2: Open File Location (Works locally on Windows)
        st.write("") # Spacer
        st.write("") # Spacer
        if st.button("📂 Open File Location"):
            # Open Windows Explorer with the file selected
            abs_path = os.path.abspath(st.session_state.downloaded_file)
            subprocess.Popen(f'explorer /select,"{abs_path}"')


