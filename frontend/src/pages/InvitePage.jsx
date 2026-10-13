import { useState, useEffect } from "react";
import { Link, useParams, useNavigate, useLocation } from "react-router-dom";
import { invites as invitesApi } from "../api/client";
import { useAuth } from "../context/AuthContext";
import { buildAuthLink, getLocationPath } from "../utils/authRedirect";
import { attemptDesktopInvite, browserInviteChoice, buildDesktopInviteLink } from "../utils/appLinks";
import { isBrowserRuntime } from "../utils/runtime";

export default function InvitePage() {
  const { code } = useParams();
  return <InvitePreview key={code} code={code} />;
}

function InvitePreview({ code }) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, loading: authLoading } = useAuth();
  const [invite, setInvite] = useState(null);
  const [error, setError] = useState(null);
  const [joining, setJoining] = useState(false);
  const [loading, setLoading] = useState(true);
  const [browserChosen, setBrowserChosen] = useState(false);
  const desktopLink = buildDesktopInviteLink(code);

  useEffect(() => {
    let disposed = false;
    invitesApi
      .preview(code)
      .then((data) => { if (!disposed) setInvite(data.invite); })
      .catch((e) => { if (!disposed) setError(e.message); })
      .finally(() => { if (!disposed) setLoading(false); });
    return () => { disposed = true; };
  }, [code]);

  useEffect(() => {
    if (invite && !loading && !authLoading && isBrowserRuntime() && import.meta.env.VITE_DESKTOP_HANDOFF_ENABLED === "true") {
      attemptDesktopInvite(code);
    }
  }, [invite, loading, authLoading, code]);

  const chooseBrowser = () => { browserInviteChoice(code); setBrowserChosen(true); };

  const handleAccept = async () => {
    if (isBrowserRuntime()) chooseBrowser();
    if (!user) {
      navigate(buildAuthLink("/login", getLocationPath(location)));
      return;
    }
    setJoining(true);
    setError(null);
    try {
      await invitesApi.accept(code);
      navigate("/");
    } catch (e) {
      setError(e.message);
    } finally {
      setJoining(false);
    }
  };

  if (loading || authLoading) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center bg-cyber-bg cyber-grid-bg noise-texture gap-4">
        <h1 className="text-3xl font-display font-bold text-neon-cyan logo-animated tracking-[0.2em]">
          SYNTH
        </h1>
        <div className="flex items-center gap-1">
          <div className="waveform-bar" />
          <div className="waveform-bar" />
          <div className="waveform-bar" />
          <div className="waveform-bar" />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-cyber-bg cyber-grid-bg noise-texture">
      <div className="glass-card p-8 w-full max-w-sm text-center">
        <h1 className="text-2xl font-display font-bold text-neon-cyan tracking-[0.15em] mb-6">
          SYNTH
        </h1>

        {error && !invite && (
          <div className="space-y-4">
            <div className="w-16 h-16 mx-auto rounded-2xl bg-neon-red/10 border border-neon-red/30
                            flex items-center justify-center text-neon-red text-2xl">
              ✕
            </div>
            <p className="text-neon-red text-sm">{error}</p>
            <button
              onClick={() => navigate("/")}
              className="w-full py-2.5 bg-cyber-panel text-cyber-text rounded-lg font-display font-semibold
                         text-sm uppercase tracking-wider hover:bg-cyber-hover transition cursor-pointer"
            >
              Go Home
            </button>
          </div>
        )}

        {invite && (
          <div className="space-y-5">
            <p className="text-cyber-muted text-xs uppercase tracking-widest font-display">
              You've been invited to join
            </p>

            {/* Server icon */}
            <div className="w-20 h-20 mx-auto rounded-2xl bg-gradient-to-br from-neon-cyan/20 to-neon-purple/20
                            border border-cyber-border/40 flex items-center justify-center
                            text-2xl font-display font-bold text-neon-cyan">
              {invite.server_icon ? (
                <img src={invite.server_icon} alt="" className="w-16 h-16 rounded-xl" />
              ) : (
                invite.server_name?.slice(0, 2)?.toUpperCase() || "??"
              )}
            </div>

            <div>
              <h2 className="text-xl font-display font-bold text-cyber-text">
                {invite.server_name}
              </h2>
              {invite.member_count != null && (
                <p className="text-cyber-muted text-xs mt-1">
                  {invite.member_count} member{invite.member_count !== 1 ? "s" : ""}
                </p>
              )}
            </div>

            {error && <p className="text-neon-red text-xs">{error}</p>}

            {isBrowserRuntime() && desktopLink && (
              <div className="space-y-2 border border-neon-cyan/30 bg-neon-cyan/5 rounded-lg p-3">
                <a href={desktopLink} className="block text-neon-cyan font-display text-sm font-semibold hover:underline">
                  Open in Synth
                </a>
                <button onClick={chooseBrowser} className="text-xs text-cyber-muted hover:text-cyber-text cursor-pointer">
                  {browserChosen ? "Continue with the invite below" : "Continue in browser"}
                </button>
                <Link to="/download?src=invite" className="block text-xs text-neon-cyan/80 hover:underline">Download Synth</Link>
              </div>
            )}

            <button
              onClick={handleAccept}
              disabled={joining}
              className="w-full py-3 rounded-lg font-display font-bold text-sm uppercase tracking-wider
                         bg-gradient-to-r from-neon-cyan to-neon-purple text-cyber-bg
                         hover:shadow-[0_0_25px_rgba(0,255,229,0.3)] transition cursor-pointer
                         disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {joining ? "Joining…" : user ? "Accept Invite" : "Log in to Join"}
            </button>

            <button
              onClick={() => navigate("/")}
              className="w-full py-2 text-cyber-muted text-xs hover:text-cyber-text transition cursor-pointer"
            >
              No thanks
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
