import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { auth as authApi } from "../api/client";

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get("token") || "";

  const [newPassword, setNewPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [done, setDone] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    if (newPassword !== confirm) {
      setError("Passwords do not match.");
      return;
    }
    setLoading(true);
    try {
      await authApi.resetPassword(token, newPassword);
      setDone(true);
      setTimeout(() => navigate("/login"), 3000);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-cyber-bg cyber-grid-bg noise-texture">
        <div className="relative z-10 w-full max-w-sm p-8 glass-card rounded-2xl shadow-2xl text-center">
          <div className="text-4xl mb-4">⊘</div>
          <p className="text-neon-red text-sm mb-2">Invalid reset link.</p>
          <p className="text-cyber-muted text-xs">
            This link is missing a token. Please request a new one.
          </p>
          <Link
            to="/forgot-password"
            className="mt-6 inline-block text-neon-cyan text-sm hover:underline font-display font-semibold"
          >
            Request new link →
          </Link>
        </div>
      </div>
    );
  }

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
            new password
          </p>
          <div className="h-px flex-1 bg-gradient-to-r from-transparent via-neon-cyan/30 to-transparent" />
        </div>

        {done ? (
          <div className="text-center space-y-4">
            <div className="w-14 h-14 mx-auto rounded-2xl bg-neon-green/10 border border-neon-green/30
                            flex items-center justify-center text-2xl">
              ✓
            </div>
            <p className="text-cyber-text text-sm">Password updated successfully!</p>
            <p className="text-cyber-muted/60 text-xs">Redirecting you to login…</p>
          </div>
        ) : (
          <>
            {error && (
              <div className="mb-4 p-3 bg-neon-red/10 border border-neon-red/30 rounded-lg text-neon-red text-sm flex items-center gap-2">
                <span className="text-xs">⚠</span> {error}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-5">
              <div>
                <label className="block text-[10px] text-cyber-muted uppercase tracking-[0.25em] mb-2 font-display font-semibold">
                  New Password
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full px-4 py-2.5 bg-cyber-bg/60 border border-cyber-border rounded-lg
                             text-cyber-text placeholder-cyber-muted/50 text-sm
                             focus:outline-none focus:border-neon-cyan/60 focus:glow-cyan
                             hover:border-cyber-muted/40 transition-all duration-300"
                  placeholder="••••••••"
                />
              </div>

              <div>
                <label className="block text-[10px] text-cyber-muted uppercase tracking-[0.25em] mb-2 font-display font-semibold">
                  Confirm Password
                </label>
                <input
                  type="password"
                  required
                  minLength={6}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full px-4 py-2.5 bg-cyber-bg/60 border border-cyber-border rounded-lg
                             text-cyber-text placeholder-cyber-muted/50 text-sm
                             focus:outline-none focus:border-neon-cyan/60 focus:glow-cyan
                             hover:border-cyber-muted/40 transition-all duration-300"
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
                {loading ? "UPDATING..." : "SET NEW PASSWORD"}
              </button>
            </form>
          </>
        )}

        <p className="mt-6 text-center text-sm text-cyber-muted">
          <Link to="/login" className="text-neon-pink hover:text-glow-pink transition-all duration-300 font-display font-semibold">
            ← Back to Login
          </Link>
        </p>
      </div>
    </div>
  );
}
