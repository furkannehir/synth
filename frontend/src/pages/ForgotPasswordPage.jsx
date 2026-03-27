import { useState } from "react";
import { Link } from "react-router-dom";
import { auth as authApi } from "../api/client";

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authApi.forgotPassword(email.trim().toLowerCase());
      setSent(true);
    } catch {
      // Show success regardless — prevents email enumeration on the frontend too
      setSent(true);
    } finally {
      setLoading(false);
    }
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
            reset access
          </p>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neon-cyan/30 to-transparent" />
        </div>

        {sent ? (
          <div className="text-center space-y-4">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-neon-green/10 border border-neon-green/30
                            flex items-center justify-center text-2xl">
              ✓
            </div>
            <p className="text-cyber-text text-sm leading-relaxed">
              If that email is registered, a reset link has been sent. Check your inbox.
            </p>
            <p className="text-cyber-muted/50 text-xs">
              Didn't receive it? Check your spam folder or{" "}
              <button
                onClick={() => { setSent(false); setEmail(""); }}
                className="text-neon-cyan hover:underline"
              >
                try again
              </button>.
            </p>
          </div>
        ) : (
          <>
            <p className="text-cyber-muted text-xs text-center mb-6 leading-relaxed">
              Enter your email and we'll send you a link to reset your password.
            </p>

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
                             hover:border-cyber-muted/40 transition-all duration-300"
                  placeholder="user@synth.net"
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
                {loading ? "SENDING..." : "SEND RESET LINK"}
              </button>
            </form>
          </>
        )}

        <p className="mt-6 text-center text-sm text-cyber-muted">
          Remembered?{" "}
          <Link to="/login" className="text-neon-pink hover:text-glow-pink transition-all duration-300 font-display font-semibold">
            Log In
          </Link>
        </p>
      </div>
    </div>
  );
}
