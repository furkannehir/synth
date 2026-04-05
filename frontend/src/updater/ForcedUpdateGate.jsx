import { useForcedUpdate } from "./checkForUpdates";

/**
 * Wraps the entire app.  While a mandatory update is downloading / installing
 * the children are hidden behind a full-screen overlay that the user cannot
 * dismiss.  If no update is available (or we're running in a browser), the
 * children render normally.
 */
export default function ForcedUpdateGate({ children }) {
  const { updating, status, progress } = useForcedUpdate();

  if (!updating) return children;

  return (
    <div style={styles.overlay}>
      <div style={styles.card}>
        {/* Logo */}
        <h1 style={styles.logo}>SYNTH</h1>

        {/* Status message */}
        <p style={styles.status}>{status}</p>

        {/* Progress bar */}
        <div style={styles.trackOuter}>
          <div
            style={{
              ...styles.trackInner,
              width: `${progress}%`,
            }}
          />
        </div>

        <p style={styles.hint}>
          Please wait — the app will restart automatically.
        </p>
      </div>
    </div>
  );
}

/* ── inline styles so this works even if CSS hasn't loaded yet ────────── */
const styles = {
  overlay: {
    position: "fixed",
    inset: 0,
    zIndex: 999999,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "linear-gradient(135deg, #0a0e17 0%, #111927 50%, #0a0e17 100%)",
    fontFamily: "'Inter', 'Segoe UI', sans-serif",
  },
  card: {
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: "1.25rem",
    padding: "3rem 4rem",
    borderRadius: "1rem",
    background: "rgba(255 255 255 / 0.04)",
    border: "1px solid rgba(255 255 255 / 0.08)",
    backdropFilter: "blur(24px)",
    boxShadow: "0 0 60px rgba(0 200 255 / 0.08)",
    maxWidth: "400px",
    width: "90%",
  },
  logo: {
    margin: 0,
    fontSize: "2rem",
    fontWeight: 700,
    letterSpacing: "0.2em",
    background: "linear-gradient(90deg, #00e5ff, #7c4dff)",
    WebkitBackgroundClip: "text",
    WebkitTextFillColor: "transparent",
  },
  status: {
    margin: 0,
    color: "rgba(255 255 255 / 0.7)",
    fontSize: "0.875rem",
    textAlign: "center",
  },
  trackOuter: {
    width: "100%",
    height: "6px",
    borderRadius: "3px",
    background: "rgba(255 255 255 / 0.1)",
    overflow: "hidden",
  },
  trackInner: {
    height: "100%",
    borderRadius: "3px",
    background: "linear-gradient(90deg, #00e5ff, #7c4dff)",
    transition: "width 0.3s ease",
  },
  hint: {
    margin: 0,
    color: "rgba(255 255 255 / 0.35)",
    fontSize: "0.75rem",
    textAlign: "center",
  },
};
