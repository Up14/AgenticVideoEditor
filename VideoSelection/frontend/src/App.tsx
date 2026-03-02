import { useState, useCallback } from "react";
import URLInput from "./components/URLInput";
import VideoPlayer from "./components/VideoPlayer";
import Timeline from "./components/Timeline";
import CaptionPanel from "./components/CaptionPanel";
import Toolbar from "./components/Toolbar";
import { useVideoSync } from "./hooks/useVideoSync";
import { useCaptions } from "./hooks/useCaptions";
import {
  processVideo,
  exportClip,
  getVideoStreamUrl,
  getDownloadUrl,
  type Caption,
  type ProcessResponse,
} from "./api/client";
import "./App.css";

/**
 * Main application — orchestrates all components and manages shared state.
 */
export default function App() {
  // ── Processing State ──
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoData, setVideoData] = useState<ProcessResponse | null>(null);

  // ── Video Sync ──
  const {
    videoRef,
    currentTime,
    duration,
    isPlaying,
    seekTo,
    togglePlay,
    handleLoadedMetadata,
  } = useVideoSync();

  // ── Selection State ──
  const [selectionStart, setSelectionStart] = useState(0);
  const [selectionEnd, setSelectionEnd] = useState(0);

  // ── Export State ──
  const [isExporting, setIsExporting] = useState(false);
  const [exportResult, setExportResult] = useState<{
    clipUrl: string;
    captionsUrl: string;
  } | null>(null);

  // ── Captions ──
  const captions: Caption[] = videoData?.captions ?? [];
  const { activeCaption, activeCaptionIndex, selectedCaptions } = useCaptions(
    captions,
    currentTime,
    selectionStart,
    selectionEnd
  );

  // ── Handlers ──

  const handleProcessUrl = useCallback(async (url: string, quality: number) => {
    setIsLoading(true);
    setError(null);
    setVideoData(null);
    setExportResult(null);

    try {
      const data = await processVideo(url, quality);
      setVideoData(data);

      // Default selection: first 30 seconds or full video if shorter
      const defaultEnd = Math.min(30, data.duration);
      setSelectionStart(0);
      setSelectionEnd(defaultEnd);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to process video");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSelectionChange = useCallback(
    (start: number, end: number) => {
      setSelectionStart(start);
      setSelectionEnd(end);
      setExportResult(null); // Clear old export when selection changes
    },
    []
  );

  const handleExport = useCallback(async () => {
    if (!videoData) return;

    setIsExporting(true);
    setError(null);

    try {
      const result = await exportClip(
        videoData.video_id,
        selectionStart,
        selectionEnd
      );
      setExportResult({
        clipUrl: getDownloadUrl(result.clip_url),
        captionsUrl: getDownloadUrl(result.captions_url),
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setIsExporting(false);
    }
  }, [videoData, selectionStart, selectionEnd]);

  const handleSeekToSelection = useCallback(() => {
    seekTo(selectionStart);
  }, [seekTo, selectionStart]);

  // ── Keyboard Shortcuts ──
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!videoData) return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          togglePlay();
          break;
        case "i":
        case "I":
          handleSelectionChange(currentTime, selectionEnd);
          break;
        case "o":
        case "O":
          handleSelectionChange(selectionStart, currentTime);
          break;
        case "ArrowLeft":
          seekTo(Math.max(0, currentTime - 5));
          break;
        case "ArrowRight":
          seekTo(Math.min(duration, currentTime + 5));
          break;
      }
    },
    [
      videoData,
      togglePlay,
      currentTime,
      selectionStart,
      selectionEnd,
      duration,
      seekTo,
      handleSelectionChange,
    ]
  );

  // ── Render ──

  return (
    <div className="app" tabIndex={0} onKeyDown={handleKeyDown}>
      {/* Header */}
      <header className="app__header">
        <h1>🎬 Video Selection Tool</h1>
        <span className="app__subtitle">
          Load a YouTube video, select a clip, export with captions
        </span>
      </header>

      {/* URL Input */}
      <URLInput onSubmit={handleProcessUrl} isLoading={isLoading} />

      {/* Loading State */}
      {isLoading && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <p>Downloading video & extracting captions...</p>
          <p className="loading-hint">This may take a minute for longer videos</p>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="error-banner">
          <span>❌ {error}</span>
          <button onClick={() => setError(null)}>Dismiss</button>
        </div>
      )}

      {/* Editor */}
      {videoData && (
        <div className="editor">
          <h2 className="editor__title">{videoData.title}</h2>

          {/* Video Player */}
          <VideoPlayer
            videoRef={videoRef}
            src={getVideoStreamUrl(videoData.video_id)}
            onLoadedMetadata={handleLoadedMetadata}
            isPlaying={isPlaying}
            onTogglePlay={togglePlay}
            currentTime={currentTime}
            duration={duration}
          />

          {/* Timeline */}
          <Timeline
            duration={duration}
            currentTime={currentTime}
            captions={captions}
            selectionStart={selectionStart}
            selectionEnd={selectionEnd}
            onSelectionChange={handleSelectionChange}
            onSeek={seekTo}
          />

          {/* Toolbar */}
          <Toolbar
            selectionStart={selectionStart}
            selectionEnd={selectionEnd}
            duration={duration}
            onSelectionChange={handleSelectionChange}
            onExport={handleExport}
            onSeekToSelection={handleSeekToSelection}
            isExporting={isExporting}
          />

          {/* Export Result */}
          {exportResult && (
            <div className="export-result">
              <h3>✅ Clip Exported!</h3>
              <div className="export-result__links">
                <a
                  href={exportResult.clipUrl}
                  download
                  className="btn-download"
                >
                  ⬇️ Download Video Clip
                </a>
                <a
                  href={exportResult.captionsUrl}
                  download
                  className="btn-download"
                >
                  📄 Download Captions JSON
                </a>
              </div>
            </div>
          )}

          {/* Caption Panel */}
          <CaptionPanel
            captions={captions}
            selectedCaptions={selectedCaptions}
            activeCaption={activeCaption}
            activeCaptionIndex={activeCaptionIndex}
            selectionStart={selectionStart}
            selectionEnd={selectionEnd}
            onSeek={seekTo}
          />

          {/* Keyboard Shortcuts Help */}
          <div className="shortcuts-hint">
            <b>Shortcuts:</b> Space = Play/Pause · I = Set In Point · O = Set
            Out Point · ← → = Seek ±5s
          </div>
        </div>
      )}
    </div>
  );
}
