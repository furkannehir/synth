import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Link, useNavigate } from "react-router-dom";
import { isBrowserRuntime } from "../utils/runtime";
import { trackEvent } from "../utils/analytics";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const showDesktopDownload = isBrowserRuntime();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await register(username, email, password);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDesktopCtaClick = () => {
    trackEvent("desktop_cta_clicked", {
      source: "register",
      placement: "register-card",
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cyber-bg cyber-grid-bg noise-texture">
      <div className="relative z-10 w-full max-w-sm p-8 glass-card rounded-2xl shadow-2xl">
        <h1 className="text-4xl font-display font-bold text-center text-neon-pink mb-1 tracking-[0.2em]"
            style={{ animation: "logo-glow-pulse 3s ease-in-out infinite", textShadow: "0 0 10px #ff00aa60, 0 0 30px #ff00aa30" }}>
          SYNTH
        </h1>
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neon-pink/30 to-transparent" />
          <p className="text-cyber-muted text-xs uppercase tracking-[0.3em]">
            create identity
          </p>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neon-pink/30 to-transparent" />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-neon-red/10 border border-neon-red/30 rounded-lg text-neon-red text-sm flex items-center gap-2">
            <span className="text-xs">⚠</span> {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-[10px] text-cyber-muted uppercase tracking-[0.25em] mb-2 font-display font-semibold">
              Username
            </label>
            <input
              type="text"
              required
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-2.5 bg-cyber-bg/60 border border-cyber-border rounded-lg
                         text-cyber-text placeholder-cyber-muted/50 text-sm
                         focus:outline-none focus:border-neon-pink/60 focus:glow-pink
                         hover:border-cyber-muted/40
                         transition-all duration-300"
              placeholder="netrunner"
            />
          </div>

          <div>
            <label className="block text-[10px] text-cyber-muted uppercase tracking-[0.25em] mb-2 font-display font-semibold">
              Email Address
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-4 py-2.5 bg-cyber-bg/60 border border-cyber-border rounded-lg
                         text-cyber-text placeholder-cyber-muted/50 text-sm
                         focus:outline-none focus:border-neon-pink/60 focus:glow-pink
                         hover:border-cyber-muted/40
                         transition-all duration-300"
              placeholder="user@synth.net"
            />
          </div>

          <div>
            <label className="block text-[10px] text-cyber-muted uppercase tracking-[0.25em] mb-2 font-display font-semibold">
              Password
            </label>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-cyber-bg/60 border border-cyber-border rounded-lg
                         text-cyber-text placeholder-cyber-muted/50 text-sm
                         focus:outline-none focus:border-neon-pink/60 focus:glow-pink
                         hover:border-cyber-muted/40
                         transition-all duration-300"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-neon-pink/15 to-neon-pink/5
                       border border-neon-pink/60 text-neon-pink
                       rounded-lg font-display font-bold uppercase tracking-[0.25em] text-sm
                       hover:from-neon-pink/25 hover:to-neon-pink/10 hover:glow-pink hover:border-neon-pink
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-all duration-300 cursor-pointer"
          >
            {loading ? "INITIALIZING..." : "REGISTER"}
          </button>
        </form>

        {showDesktopDownload && (
          <div className="mt-5 rounded-xl border border-neon-cyan/30 bg-neon-cyan/5 p-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-cyber-muted">
              Want the full native experience?
            </p>
            <Link
              to="/download?src=register"
              onClick={handleDesktopCtaClick}
              className="mt-2 inline-flex items-center gap-2 text-xs font-display font-semibold uppercase tracking-[0.2em] text-neon-cyan transition-all duration-300 hover:text-glow-cyan"
            >
              Download Desktop App
              <span aria-hidden="true">↗</span>
            </Link>
          </div>
        )}

        <div className="mt-6 flex items-center gap-3">
          <div className="h-px flex-1 bg-cyber-border" />
          <span className="text-[10px] text-cyber-muted uppercase tracking-widest">or</span>
          <div className="h-px flex-1 bg-cyber-border" />
        </div>

        <p className="mt-4 text-center text-sm text-cyber-muted">
          Already jacked in?{" "}
          <Link to="/login" className="text-neon-cyan hover:text-glow-cyan transition-all duration-300 font-display font-semibold">
            Log in
          </Link>
        </p>
      </div>
    </div>
  );
}
