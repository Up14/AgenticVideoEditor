import { useState } from "react";

interface Props {
  onSubmit: (url: string, quality: number) => void;
  isLoading: boolean;
}

/**
 * URL input form — takes a YouTube URL and quality selection.
 */
export default function URLInput({ onSubmit, isLoading }: Props) {
  const [url, setUrl] = useState("");
  const [quality, setQuality] = useState(720);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) {
      onSubmit(url.trim(), quality);
    }
  };

  return (
    <form className="url-input" onSubmit={handleSubmit}>
      <div className="url-input__field">
        <label htmlFor="yt-url">YouTube URL</label>
        <input
          id="yt-url"
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://www.youtube.com/watch?v=..."
          disabled={isLoading}
          autoFocus
        />
      </div>

      <div className="url-input__options">
        <label htmlFor="quality">Quality</label>
        <select
          id="quality"
          value={quality}
          onChange={(e) => setQuality(Number(e.target.value))}
          disabled={isLoading}
        >
          <option value={1080}>1080p</option>
          <option value={720}>720p</option>
          <option value={480}>480p</option>
          <option value={360}>360p</option>
        </select>
      </div>

      <button type="submit" disabled={isLoading || !url.trim()}>
        {isLoading ? "Processing..." : "Load Video"}
      </button>
    </form>
  );
}
