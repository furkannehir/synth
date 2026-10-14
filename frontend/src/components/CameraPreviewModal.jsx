import { useEffect, useRef, useState } from "react";
import { useLocalParticipant } from "@livekit/components-react";
import { Room, Track, createLocalVideoTrack } from "livekit-client";
import Modal from "./Modal";
import FullscreenVideo from "./FullscreenVideo";

function cameraError(error) {
  if (error.name === "NotAllowedError") return "Camera access was blocked. Allow camera access, then retry.";
  if (error.name === "NotFoundError") return "No camera is available. Connect a camera and retry.";
  if (error.name === "NotReadableError") return "This camera is unavailable or in use. Choose another source or retry.";
  if (error.name === "OverconstrainedError") return "This video source is unavailable. Choose another camera.";
  return error.message || "Could not access the camera.";
}

export default function CameraPreviewModal({ onPublished, onCancel }) {
  const { localParticipant } = useLocalParticipant();
  const videoRef = useRef(null);
  const resourceRef = useRef(null);
  const [deviceId, setDeviceId] = useState("");
  const [devices, setDevices] = useState([]);
  const [retry, setRetry] = useState(0);
  const [preview, setPreview] = useState({ loading: true, ready: false, deviceId: "", error: "" });
  const [deviceWarning, setDeviceWarning] = useState("");
  const [publishError, setPublishError] = useState("");
  const [publishing, setPublishing] = useState(false);

  useEffect(() => {
    const resource = { track: null, disposed: false, publishing: false, transferred: false };
    resourceRef.current = resource;
    const video = videoRef.current;
    const mediaDevices = navigator.mediaDevices;
    let deviceRequest = 0;
    const refreshDevices = async () => {
      const request = ++deviceRequest;
      try {
        const available = await Room.getLocalDevices("videoinput", false);
        if (resource.disposed || request !== deviceRequest) return;
        setDevices(available.filter((device) => device.deviceId));
        setDeviceWarning("");
      } catch {
        if (!resource.disposed && request === deviceRequest) setDeviceWarning("Could not list video sources. You can still use the current preview.");
      }
    };
    const onEnded = () => {
      if (!resource.disposed && !resource.transferred) setPreview((current) => ({ ...current, ready: false, error: "This camera disconnected. Choose another source or retry." }));
    };
    async function startPreview() {
      try {
        const track = await createLocalVideoTrack({
          ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "user" }),
          resolution: { width: 1280, height: 720 },
        });
        if (resource.disposed) { track.stop(); return; }
        resource.track = track;
        track.attach(video);
        track.mediaStreamTrack.addEventListener("ended", onEnded);
        const actualDeviceId = track.mediaStreamTrack.getSettings().deviceId || deviceId;
        setPreview({ loading: false, ready: true, deviceId: actualDeviceId, error: "" });
        await refreshDevices();
      } catch (error) {
        if (!resource.disposed) {
          resource.track?.detach(video);
          resource.track?.stop();
          resource.track = null;
          setPreview({ loading: false, ready: false, deviceId, error: cameraError(error) });
        }
      }
    }
    refreshDevices();
    startPreview();
    mediaDevices?.addEventListener("devicechange", refreshDevices);
    return () => {
      resource.disposed = true;
      mediaDevices?.removeEventListener("devicechange", refreshDevices);
      resource.track?.mediaStreamTrack.removeEventListener("ended", onEnded);
      resource.track?.detach(video);
      if (!resource.transferred && !resource.publishing) resource.track?.stop();
    };
  }, [deviceId, retry]);

  const restartPreview = (nextDeviceId = deviceId) => {
    setPreview({ loading: true, ready: false, deviceId: nextDeviceId, error: "" });
    setPublishError("");
    if (nextDeviceId === deviceId) setRetry((current) => current + 1);
    else setDeviceId(nextDeviceId);
  };

  const publish = async () => {
    const resource = resourceRef.current;
    if (!localParticipant || !resource?.track || resource.publishing || !preview.ready) return;
    resource.publishing = true;
    setPublishing(true);
    setPublishError("");
    try {
      const previousTrack = localParticipant.getTrackPublication(Track.Source.Camera)?.track;
      if (previousTrack && previousTrack !== resource.track) await localParticipant.unpublishTrack(previousTrack, true);
      if (resource.disposed) { resource.track.stop(); return; }
      await localParticipant.publishTrack(resource.track, { source: Track.Source.Camera });
      if (resource.disposed) {
        await localParticipant.unpublishTrack(resource.track, true);
        resource.track.stop();
        return;
      }
      resource.transferred = true;
      onPublished();
    } catch (error) {
      if (resource.disposed) resource.track.stop();
      else {
        setPublishError(error.message || "Could not publish the camera. Please try again.");
        setPublishing(false);
      }
    } finally {
      resource.publishing = false;
    }
  };

  const selectedDevice = deviceId || preview.deviceId;
  const listedSelection = devices.some((device) => device.deviceId === selectedDevice);
  return (
    <Modal title="Camera preview" id="camera-preview-title" className="media-preview-modal camera-preview-modal" onClose={onCancel}>
      <div className="media-preview-source">
        <p>Check your appearance before publishing to the room.</p>
        <label>Video source
          <select value={selectedDevice} disabled={publishing || devices.length === 0} onChange={(event) => restartPreview(event.target.value)}>
            {!listedSelection && <option value={selectedDevice}>{selectedDevice ? "Current camera" : "Default camera"}</option>}
            {devices.map((device, index) => <option key={device.deviceId} value={device.deviceId}>{device.label || `Camera ${index + 1}`}</option>)}
          </select>
        </label>
        {deviceWarning && <p role="status">{deviceWarning}</p>}
      </div>
      <FullscreenVideo className={`media-preview-media ${preview.ready ? "" : "is-pending"}`} label="camera preview" disabled={!preview.ready}>
        <video ref={videoRef} autoPlay muted playsInline aria-label="Camera preview" data-lk-local-video="true" />
        {preview.loading && <p className="media-preview-status" role="status">Starting camera…</p>}
        {preview.error && <div className="media-preview-status"><p role="alert">{preview.error}</p><button onClick={() => restartPreview()} disabled={publishing}>Retry</button></div>}
      </FullscreenVideo>
      <footer className="media-preview-footer">
        {publishError && <p role="alert" className="form-error">{publishError}</p>}
        <div><button onClick={onCancel}>Cancel</button><button className="primary-button" onClick={publish} disabled={!preview.ready || publishing || !localParticipant}>{publishing ? "Publishing…" : "Publish camera"}</button></div>
      </footer>
    </Modal>
  );
}
