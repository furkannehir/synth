import { useAuth } from "../context/AuthContext";

export default function SessionStatus({ children }) {
  const { startupError, retryStartup, loading } = useAuth();
  if (!startupError) return children;
  return (
    <div className="min-h-screen flex items-center justify-center bg-cyber-bg text-cyber-text p-6">
      <div className="glass-card p-8 max-w-sm text-center space-y-4">
        <h1 className="font-display text-xl text-neon-cyan">Reconnect to Synth</h1>
        <p className="text-sm text-cyber-muted" role="alert">{startupError}</p>
        <button onClick={retryStartup} disabled={loading}
          className="px-5 py-2 rounded-lg border border-neon-cyan text-neon-cyan cursor-pointer disabled:opacity-50">
          {loading ? "Connecting…" : "Retry"}
        </button>
      </div>
    </div>
  );
}
