import { useEffect, useRef, useState } from "react";
import { Monitor } from "lucide-react";
import { useLocalParticipant } from "@livekit/components-react";
import { Track, createLocalScreenTracks } from "livekit-client";
import Modal from "./Modal";
import { createNativeScreenTrack, isNativeScreenCaptureSupported } from "../utils/nativeScreenCapture";
import useNativeCaptureSources from "../hooks/useNativeCaptureSources";
import CaptureSourceOptions from "./CaptureSourceOptions";
import FullscreenVideo from "./FullscreenVideo";

function captureError(error) {
  if (error.name === "NotAllowedError" || error.name === "AbortError") return "No screen selected. Choose a source to try again.";
  if (error.name === "NotReadableError") return "This source is unavailable. Choose another screen or window.";
  return error.message || "Could not access screen sharing. Choose a source to try again.";
}

function releasePreview(resource, video) {
  resource.abortController?.abort();
  resource.track?.mediaStreamTrack.removeEventListener("ended", resource.onEnded);
  resource.track?.detach(video);
  resource.track?.stop();
  resource.track = null;
  resource.ready = false;
}

export default function ScreenSharePreviewModal({ onPublished, onCancel }) {
  const { localParticipant } = useLocalParticipant();
  const videoRef = useRef(null);
  const resourceRef = useRef(null);
  const [preview, setPreview] = useState({ ready: false, choosing: false, label: "", error: "" });
  const [publishing, setPublishing] = useState(false);
  const [publishError, setPublishError] = useState("");
  const nativeCapture = isNativeScreenCaptureSupported();
  const [sourceId, setSourceId] = useState("");
  const { sources, loading: sourcesLoading, error: sourceError, refresh, refreshQuiet } = useNativeCaptureSources({ enabled: nativeCapture, paused: preview.choosing || publishing });
  const selectedSourceId = sources.some((source) => source.id === sourceId) ? sourceId : "";

  useEffect(() => {
    const resource = { track: null, ready: false, choosing: false, publishing: false, transferred: false, disposed: false, onEnded: null };
    resourceRef.current = resource;
    const video = videoRef.current;
    return () => {
      resource.disposed = true;
      resource.track?.mediaStreamTrack.removeEventListener("ended", resource.onEnded);
      resource.track?.detach(video);
      if (!resource.transferred && !resource.publishing) { resource.abortController?.abort(); resource.track?.stop(); }
    };
  }, []);

  const chooseSource = async (nextSourceId = selectedSourceId) => {
    const resource = resourceRef.current;
    if (!resource || resource.disposed || resource.choosing || resource.publishing) return;
    resource.choosing = true;
    if (nativeCapture) {
      releasePreview(resource, videoRef.current);
      setPreview({ ready: false, choosing: true, label: "", error: "" });
    } else setPreview((current) => ({ ...current, choosing: true, error: "" }));
    setPublishError("");
    let selectedTrack;
    try {
      // Keep this call in the click handler: the native picker needs user activation.
      resource.abortController = new AbortController();
      const tracks = nativeCapture
        ? [await createNativeScreenTrack(nextSourceId, { signal: resource.abortController.signal })]
        : await createLocalScreenTracks({ audio: false });
      selectedTrack = tracks.find((track) => track.source === Track.Source.ScreenShare);
      for (const track of tracks) if (track !== selectedTrack) track.stop();
      if (!selectedTrack) throw new Error("No video source was selected. Please try again.");
      if (resource.disposed) { selectedTrack.stop(); return; }

      resource.track?.mediaStreamTrack.removeEventListener("ended", resource.onEnded);
      resource.track?.detach(videoRef.current);
      resource.track?.stop();
      resource.track = selectedTrack;
      resource.ready = true;
      resource.onEnded = () => {
        if (resource.disposed || resource.transferred) return;
        resource.ready = false;
        setPreview((current) => ({ ...current, ready: false, error: "This screen share ended. Choose a source to try again." }));
      };
      selectedTrack.attach(videoRef.current);
      selectedTrack.mediaStreamTrack.addEventListener("ended", resource.onEnded);
      const surface = selectedTrack.mediaStreamTrack.getSettings().displaySurface;
      const label = selectedTrack.nativeCaptureLabel || selectedTrack.mediaStreamTrack.label || ({ monitor: "Screen", window: "Window", browser: "Browser tab" })[surface] || "Selected source";
      setPreview({ ready: true, choosing: false, label, error: "" });
    } catch (error) {
      if (selectedTrack && resource.track === selectedTrack) {
        selectedTrack.detach(videoRef.current);
        selectedTrack.stop();
        resource.track = null;
        resource.ready = false;
      }
      if (!resource.disposed) setPreview((current) => ({ ...current, ready: resource.ready, choosing: false, error: captureError(error) }));
    } finally {
      resource.choosing = false;
    }
  };

  const selectSource = (nextSourceId) => {
    const resource = resourceRef.current;
    if (!resource || resource.disposed || resource.choosing || resource.publishing) return;
    setSourceId(nextSourceId);
    if (nextSourceId) void chooseSource(nextSourceId);
    else {
      releasePreview(resource, videoRef.current);
      setPreview({ ready: false, choosing: false, label: "", error: "" });
      setPublishError("");
    }
  };

  const publish = async () => {
    const resource = resourceRef.current;
    if (!localParticipant || !resource?.track || !resource.ready || resource.choosing || resource.publishing || resource.disposed || (nativeCapture && !selectedSourceId)) return;
    resource.publishing = true;
    setPublishing(true);
    setPublishError("");
    try {
      const previousTrack = localParticipant.getTrackPublication(Track.Source.ScreenShare)?.track;
      if (previousTrack && previousTrack !== resource.track) await localParticipant.unpublishTrack(previousTrack, true);
      if (resource.disposed) { resource.track.stop(); return; }
      if (!resource.ready) throw new Error("This screen share ended. Choose another source.");
      await localParticipant.publishTrack(resource.track, { source: Track.Source.ScreenShare });
      if (resource.disposed || !resource.ready) {
        await localParticipant.unpublishTrack(resource.track, true);
        resource.track.stop();
        if (!resource.disposed) throw new Error("This screen share ended. Choose another source.");
        return;
      }
      resource.transferred = true;
      onPublished();
    } catch (error) {
      if (resource.disposed) resource.track.stop();
      else {
        setPublishError(error.message || "Could not publish the screen. Please try again.");
        setPublishing(false);
      }
    } finally {
      resource.publishing = false;
    }
  };

  return (
    <Modal title="Screen share preview" id="screen-preview-title" className="media-preview-modal screen-share-preview-modal" onClose={onCancel}>
      <div className="media-preview-source">
        <p>{nativeCapture ? "Choose a window or screen to preview before publishing. Video only." : "Choose a screen, window, or tab. Check the preview before publishing to the room."}</p>
        {nativeCapture && <div className="native-source-picker"><label>Source to share
          <select value={selectedSourceId} onFocus={refreshQuiet} onChange={(event) => selectSource(event.target.value)} disabled={sourcesLoading || preview.choosing || publishing}>
            <CaptureSourceOptions sources={sources} />
          </select>
        </label><button onClick={refresh} disabled={sourcesLoading || preview.choosing || publishing}>{sourcesLoading ? "Refreshing…" : "Refresh sources"}</button></div>}
        {sourceError && <p role="alert" className="form-error">{sourceError}</p>}
        {!nativeCapture && <div className="screen-preview-source-row">
          <span title={preview.label}>{preview.label || "No source selected"}</span>
          <button onClick={() => chooseSource()} disabled={preview.choosing || publishing}>{preview.choosing ? "Choosing…" : preview.ready ? "Change source" : "Choose source"}</button>
        </div>}
        {preview.ready && preview.error && <p role="alert" className="form-error">{preview.error} Your previous source is still selected.</p>}
      </div>
      <FullscreenVideo className={`media-preview-media ${preview.ready ? "" : "is-pending"}`} label="screen share preview" disabled={!preview.ready}>
        <video ref={videoRef} autoPlay muted playsInline aria-label="Screen share preview" />
        {!preview.ready && <div className="media-preview-status">
          <Monitor size={36} aria-hidden="true" />
          {preview.error ? <p role="alert">{preview.error}</p> : <p role="status">{preview.choosing ? (nativeCapture ? "Starting preview…" : "Select a source in the sharing window…") : "Choose a source to see its preview here."}</p>}
          {nativeCapture && preview.error && selectedSourceId && <button onClick={() => chooseSource()} disabled={preview.choosing || publishing}>Retry preview</button>}
        </div>}
      </FullscreenVideo>
      <footer className="media-preview-footer">
        {publishError && <p role="alert" className="form-error">{publishError}</p>}
        <div><button onClick={onCancel}>Cancel</button><button className="primary-button" onClick={publish} disabled={!preview.ready || preview.choosing || publishing || !localParticipant || (nativeCapture && !selectedSourceId)}>{publishing ? "Publishing…" : "Publish screen"}</button></div>
      </footer>
    </Modal>
  );
}
