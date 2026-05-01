import subprocess

url = input("Enter YouTube URL: ")
quality = input("Enter max height (360, 720, 1080): ")

cmd = [
    "yt-dlp",
    f"-f", f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]",
    "--merge-output-format", "mp4",
    url
]

subprocess.run(cmd)
