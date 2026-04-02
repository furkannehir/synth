import { useState } from "react";
import { useAuth } from "../context/AuthContext";
import { Link, useNavigate } from "react-router-dom";
import { isBrowserRuntime } from "../utils/runtime";
import { trackEvent } from "../utils/analytics";

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const showDesktopDownload = isBrowserRuntime();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/");
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const handleDesktopCtaClick = () => {
    trackEvent("desktop_cta_clicked", {
      source: "login",
      placement: "login-card",
    });
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-cyber-bg cyber-grid-bg noise-texture">
      <div className="relative z-10 w-full max-w-sm p-8 glass-card rounded-2xl shadow-2xl">
        {/* Logo */}
        <h1 className="text-4xl font-display font-bold text-center text-neon-cyan logo-animated mb-1 tracking-[0.2em]">
          SYNTH
        </h1>
        <div className="flex items-center gap-3 justify-center mb-8">
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neon-cyan/30 to-transparent" />
          <p className="text-cyber-muted text-xs uppercase tracking-[0.3em]">
            jack in
          </p>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neon-cyan/30 to-transparent" />
        </div>

        {error && (
          <div className="mb-4 p-3 bg-neon-red/10 border border-neon-red/30 rounded-lg text-neon-red text-sm flex items-center gap-2">
            <span className="text-xs">⚠</span> {error}
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
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
                         focus:outline-none focus:border-neon-cyan/60 focus:glow-cyan
                         hover:border-cyber-muted/40
                         transition-all duration-300"
              placeholder="user@synth.net"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="block text-[10px] text-cyber-muted uppercase tracking-[0.25em] font-display font-semibold">
                Password
              </label>
              <Link
                to="/forgot-password"
                className="text-[10px] text-neon-cyan/70 hover:text-neon-cyan uppercase tracking-[0.15em] font-display transition-colors duration-200"
              >
                Forgot password?
              </Link>
            </div>
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-2.5 bg-cyber-bg/60 border border-cyber-border rounded-lg
                         text-cyber-text placeholder-cyber-muted/50 text-sm
                         focus:outline-none focus:border-neon-cyan/60 focus:glow-cyan
                         hover:border-cyber-muted/40
                         transition-all duration-300"
              placeholder="••••••••"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 bg-gradient-to-r from-neon-cyan/15 to-neon-cyan/5
                       border border-neon-cyan/60 text-neon-cyan
                       rounded-lg font-display font-bold uppercase tracking-[0.25em] text-sm
                       hover:from-neon-cyan/25 hover:to-neon-cyan/10 hover:glow-cyan hover:border-neon-cyan
                       disabled:opacity-40 disabled:cursor-not-allowed
                       transition-all duration-300 cursor-pointer"
          >
            {loading ? "CONNECTING..." : "LOG IN"}
          </button>
        </form>

        {showDesktopDownload && (
          <div className="mt-5 rounded-xl border border-neon-cyan/30 bg-neon-cyan/5 p-4">
            <p className="text-[10px] uppercase tracking-[0.22em] text-cyber-muted">
              Better with native performance
            </p>
            <Link
              to="/download?src=login"
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
          No account?{" "}
          <Link to="/register" className="text-neon-pink hover:text-glow-pink transition-all duration-300 font-display font-semibold">
            Register
          </Link>
        </p>
      </div>
    </div>
  );
}
