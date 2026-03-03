import { useState, useCallback, useMemo } from "react";
import URLInput from "./components/URLInput";
import VideoPlayer from "./components/VideoPlayer";
import Timeline from "./components/Timeline";
import CaptionPanel from "./components/CaptionPanel";
import Toolbar from "./components/Toolbar";
import { useVideoSync } from "./hooks/useVideoSync";
import { useCaptions } from "./hooks/useCaptions";
import {
  processVideo,
  exportMultipleClips,
  analyzeClips,
  exportClipsCSV,
  getVideoStreamUrl,
  getDownloadUrl,
  type Caption,
  type ProcessResponse,
  type SegmentExportResult,
} from "./api/client";
import type { Segment } from "./types";
import {
  generateId,
  getSegmentColor,
  mergeOverlappingSegments,
  formatTime,
} from "./types";
import "./App.css";

/**
 * Main application — orchestrates all components with multi-segment support.
 */
export default function App() {
  // ── Processing State ──
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoData, setVideoData] = useState<ProcessResponse | null>(null);

  // ── Segment State ──
  const [segments, setSegments] = useState<Segment[]>([]);
  const [activeSegmentId, setActiveSegmentId] = useState<string | null>(null);

  // Get the active segment's bounds for playback constraint
  const activeSegment = useMemo(
    () => segments.find((s) => s.id === activeSegmentId) ?? null,
    [segments, activeSegmentId]
  );

  // ── Video Sync (constrained to active segment) ──
  const {
    videoRef,
    currentTime,
    duration,
    isPlaying,
    seekTo,
    togglePlay,
    handleLoadedMetadata,
  } = useVideoSync(activeSegment?.start ?? 0, activeSegment?.end ?? 0);

  // ── Export State ──
  const [isExporting, setIsExporting] = useState(false);
  const [exportResults, setExportResults] = useState<SegmentExportResult[] | null>(null);

  // ── Clip Selector State ──
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [isCsvExporting, setIsCsvExporting] = useState(false);

  // ── Captions ──
  const captions: Caption[] = videoData?.captions ?? [];
  const { activeCaption, activeCaptionIndex } = useCaptions(
    captions,
    currentTime,
    activeSegment?.start ?? 0,
    activeSegment?.end ?? 0
  );

  // ── Handlers ──

  const handleProcessUrl = useCallback(async (url: string, quality: number) => {
    setIsLoading(true);
    setError(null);
    setVideoData(null);
    setExportResults(null);
    setSegments([]);
    setActiveSegmentId(null);

    try {
      const data = await processVideo(url, quality);
      setVideoData(data);

      // Create initial segment while AI analysis runs
      const firstSeg: Segment = {
        id: generateId(),
        start: 0,
        end: Math.min(30, data.duration),
        color: getSegmentColor(0).color,
        label: "Clip 1",
      };
      setSegments([firstSeg]);
      setActiveSegmentId(firstSeg.id);

      // Auto-run AI clip analysis — replaces segments once done
      setIsAnalyzing(true);
      try {
        const clipData = await analyzeClips(data.video_id);
        if (clipData.clips.length > 0) {
          const aiSegments: Segment[] = clipData.clips.map((clip, i) => ({
            id: generateId(),
            start: clip.start,
            end: clip.end,
            color: getSegmentColor(i).color,
            label: clip.title || `Clip ${i + 1}`,
          }));
          setSegments(aiSegments);
          setActiveSegmentId(aiSegments[0].id);
        }
      } catch {
        // AI analysis failed — keep the initial segment, don't block the user
        console.warn("AI clip analysis failed — using default segment.");
      } finally {
        setIsAnalyzing(false);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to process video");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const handleSegmentChange = useCallback(
    (id: string, start: number, end: number) => {
      setSegments((prev) => {
        const updated = prev.map((seg) =>
          seg.id === id ? { ...seg, start, end } : seg
        );
        // Merge overlapping segments
        return mergeOverlappingSegments(updated);
      });
      setExportResults(null);
    },
    []
  );

  const handleAddSegment = useCallback(() => {
    if (!videoData) return;

    setSegments((prev) => {
      const idx = prev.length;
      // Place new segment after the last one, or at the end of video
      const lastEnd = prev.length > 0 ? prev[prev.length - 1].end : 0;
      const newStart = Math.min(lastEnd + 5, videoData.duration - 10);
      const newEnd = Math.min(newStart + 30, videoData.duration);

      if (newEnd - newStart < 1) return prev; // not enough room

      const newSeg: Segment = {
        id: generateId(),
        start: newStart,
        end: newEnd,
        color: getSegmentColor(idx).color,
        label: `Clip ${idx + 1}`,
      };

      const updated = [...prev, newSeg];
      setActiveSegmentId(newSeg.id);
      return mergeOverlappingSegments(updated);
    });
    setExportResults(null);
  }, [videoData]);

  const handleRemoveSegment = useCallback(
    (id: string) => {
      setSegments((prev) => {
        const filtered = prev.filter((s) => s.id !== id);
        // Re-label remaining segments
        return filtered.map((seg, i) => ({
          ...seg,
          label: `Clip ${i + 1}`,
          color: getSegmentColor(i).color,
        }));
      });

      // If we removed the active segment, select the first remaining one
      if (activeSegmentId === id) {
        setSegments((prev) => {
          if (prev.length > 0) setActiveSegmentId(prev[0].id);
          else setActiveSegmentId(null);
          return prev;
        });
      }
      setExportResults(null);
    },
    [activeSegmentId]
  );

  const handleExport = useCallback(async () => {
    if (!videoData || segments.length === 0) return;

    setIsExporting(true);
    setError(null);

    try {
      const result = await exportMultipleClips(
        videoData.video_id,
        segments.map((s) => ({ label: s.label, start: s.start, end: s.end }))
      );
      setExportResults(result.segments);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Export failed");
    } finally {
      setIsExporting(false);
    }
  }, [videoData, segments]);

  const handleDownloadCsv = useCallback(async () => {
    if (!videoData || segments.length === 0) return;
    setIsCsvExporting(true);
    try {
      const blob = await exportClipsCSV(
        videoData.video_id,
        segments.map((s) => ({ label: s.label, start: s.start, end: s.end }))
      );
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `clips_${videoData.video_id}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (e) {
      setError(e instanceof Error ? e.message : "CSV export failed");
    } finally {
      setIsCsvExporting(false);
    }
  }, [videoData, segments]);

  const handleSeekToSegment = useCallback(
    (id: string) => {
      const seg = segments.find((s) => s.id === id);
      if (seg) {
        setActiveSegmentId(id);
        seekTo(seg.start);
      }
    },
    [segments, seekTo]
  );

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
          if (activeSegmentId) {
            const seg = segments.find((s) => s.id === activeSegmentId);
            if (seg) handleSegmentChange(activeSegmentId, currentTime, seg.end);
          }
          break;
        case "o":
        case "O":
          if (activeSegmentId) {
            const seg = segments.find((s) => s.id === activeSegmentId);
            if (seg) handleSegmentChange(activeSegmentId, seg.start, currentTime);
          }
          break;
        case "ArrowLeft":
          seekTo(Math.max(0, currentTime - 5));
          break;
        case "ArrowRight":
          seekTo(Math.min(duration, currentTime + 5));
          break;
        case "n":
        case "N":
          handleAddSegment();
          break;
      }
    },
    [
      videoData,
      togglePlay,
      currentTime,
      activeSegmentId,
      segments,
      duration,
      seekTo,
      handleSegmentChange,
      handleAddSegment,
    ]
  );

  // ── Render ──

  return (
    <div className="app" tabIndex={0} onKeyDown={handleKeyDown}>
      {/* Header */}
      <header className="app__header">
        <h1>🎬 Video Selection Tool</h1>
        <span className="app__subtitle">
          Load a YouTube video, select multiple clips, export with captions
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

      {/* AI Analysis Banner */}
      {isAnalyzing && (
        <div className="loading-overlay">
          <div className="loading-spinner" />
          <p>🤖 AI is finding the best viral clips...</p>
          <p className="loading-hint">Analysing transcript, scoring hooks &amp; emotions</p>
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
            segments={segments}
            activeSegmentId={activeSegmentId}
            onSegmentChange={handleSegmentChange}
            onSegmentSelect={setActiveSegmentId}
            onSeek={seekTo}
          />

          {/* Toolbar */}
          <Toolbar
            segments={segments}
            activeSegmentId={activeSegmentId}
            duration={duration}
            onSegmentChange={handleSegmentChange}
            onAddSegment={handleAddSegment}
            onRemoveSegment={handleRemoveSegment}
            onSelectSegment={setActiveSegmentId}
            onExport={handleExport}
            onSeekToSegment={handleSeekToSegment}
            isExporting={isExporting}
          />

          {/* Download CSV button */}
          {segments.length > 0 && (
            <div style={{ display: "flex", justifyContent: "flex-end", margin: "8px 0" }}>
              <button
                className="btn-secondary"
                onClick={handleDownloadCsv}
                disabled={isCsvExporting}
                title="Download timestamps + captions as CSV"
              >
                {isCsvExporting ? "⏳ Preparing CSV..." : "📄 Download CSV"}
              </button>
            </div>
          )}

          {/* Export Results */}
          {exportResults && (
            <div className="export-result">
              <h3>✅ {exportResults.length} Clip{exportResults.length > 1 ? "s" : ""} Exported!</h3>
              <div className="export-result__grid">
                {exportResults.map((result, i) => {
                  const palette = getSegmentColor(i);
                  return (
                    <div key={i} className="export-result__item" style={{ borderLeftColor: palette.color }}>
                      <div className="export-result__label" style={{ color: palette.color }}>
                        {result.label} ({formatTime(result.start)} → {formatTime(result.end)})
                      </div>
                      <div className="export-result__links">
                        <a href={getDownloadUrl(result.clip_url)} download className="btn-download">
                          ⬇️ Video
                        </a>
                        <a href={getDownloadUrl(result.captions_url)} download className="btn-download btn-download--secondary">
                          📄 Captions
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* Caption Panel */}
          <CaptionPanel
            captions={captions}
            segments={segments}
            activeCaption={activeCaption}
            activeCaptionIndex={activeCaptionIndex}
            onSeek={seekTo}
          />

          {/* Keyboard Shortcuts Help */}
          <div className="shortcuts-hint">
            <b>Shortcuts:</b> Space = Play/Pause · I = Set In · O = Set
            Out · N = New Segment · ← → = Seek ±5s
          </div>
        </div>
      )}
    </div>
  );
}
