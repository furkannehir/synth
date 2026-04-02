import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { trackEvent } from "../utils/analytics";

const REPO = "furkannehir/synth";
const SOURCE_LABELS = {
  login: "from the login screen",
  register: "after registration",
  "home-banner": "from the in-app web banner",
  sidebar: "from the in-app shortcut",
};

function formatSize(bytes) {
  if (!bytes || bytes < 0) return "Unknown size";
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getAsset(release, matcher) {
  return release?.assets?.find(matcher) || null;
}

export default function DownloadPage() {
  const location = useLocation();
  const [release, setRelease] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const source = useMemo(
    () => new URLSearchParams(location.search).get("src") || "",
    [location.search]
  );
  const sourceLabel = source && SOURCE_LABELS[source] ? SOURCE_LABELS[source] : "";
  const sourceKey = source && SOURCE_LABELS[source] ? source : "direct";

  useEffect(() => {
    trackEvent("desktop_download_page_viewed", {
      source: sourceKey,
    });
  }, [sourceKey]);

  const handleDownloadClick = (target) => {
    trackEvent("desktop_download_clicked", {
      source: sourceKey,
      platform: target.id,
      asset: target.asset?.name || "",
      releaseTag: release?.tag_name || "",
    });
  };

  const handleViewAllReleasesClick = () => {
    trackEvent("desktop_releases_link_clicked", {
      source: sourceKey,
    });
  };

  const handleOpenAppClick = () => {
    trackEvent("desktop_open_app_clicked", {
      source: sourceKey,
    });
  };

  useEffect(() => {
    let ignore = false;

    async function loadRelease() {
      setLoading(true);
      setError("");

      try {
        const response = await fetch(
          `https://api.github.com/repos/${REPO}/releases/latest`,
          {
            headers: {
              Accept: "application/vnd.github+json",
            },
          }
        );

        if (!response.ok) {
          throw new Error("Could not fetch the latest release from GitHub.");
        }

        const data = await response.json();

        if (!ignore) {
          setRelease(data);
        }
      } catch (fetchError) {
        if (!ignore) {
          setError(fetchError.message || "Failed to load release data.");
        }
      } finally {
        if (!ignore) {
          setLoading(false);
        }
      }
    }

    loadRelease();

    return () => {
      ignore = true;
    };
  }, []);

  const targets = useMemo(() => {
    if (!release) return [];

    return [
      {
        id: "windows",
        title: "Windows",
        subtitle: "x64 installer",
        accent: "text-neon-cyan",
        border: "border-neon-cyan/30",
        asset:
          getAsset(release, (a) => a.name.endsWith(".exe") && a.name.includes("setup")) ||
          getAsset(release, (a) => a.name.endsWith(".msi")) ||
          getAsset(release, (a) => a.name.endsWith(".exe")),
      },
      {
        id: "macos-arm",
        title: "macOS",
        subtitle: "Apple Silicon",
        accent: "text-neon-pink",
        border: "border-neon-pink/30",
        asset: getAsset(
          release,
          (a) => a.name.endsWith(".dmg") && /aarch64|arm64/i.test(a.name)
        ),
      },
      {
        id: "macos-intel",
        title: "macOS",
        subtitle: "Intel",
        accent: "text-neon-purple",
        border: "border-neon-purple/30",
        asset: getAsset(
          release,
          (a) => a.name.endsWith(".dmg") && /x64|x86_64/i.test(a.name)
        ),
      },
      {
        id: "linux",
        title: "Linux",
        subtitle: "AppImage / .deb",
        accent: "text-neon-green",
        border: "border-neon-green/30",
        asset:
          getAsset(release, (a) => a.name.endsWith(".AppImage")) ||
          getAsset(release, (a) => a.name.endsWith(".deb")),
      },
    ];
  }, [release]);

  return (
    <div className="min-h-screen bg-cyber-bg cyber-grid-bg noise-texture px-4 py-10">
      <div className="mx-auto w-full max-w-4xl">
        <header className="mb-8 rounded-2xl border border-cyber-border bg-cyber-surface/80 p-6 backdrop-blur-md">
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <p className="mb-2 text-[11px] uppercase tracking-[0.3em] text-cyber-muted">
                Official Desktop Downloads
              </p>
              <h1 className="font-display text-4xl font-bold tracking-[0.18em] text-neon-cyan logo-animated">
                SYNTH
              </h1>
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-[0.24em] text-cyber-muted">Latest release</p>
              <p className="font-display text-2xl font-semibold text-cyber-text">
                {release?.tag_name || "..."}
              </p>
            </div>
          </div>
          <p className="mt-5 max-w-2xl text-sm text-cyber-muted">
            Install the latest desktop build from GitHub Releases. These links update automatically every time
            a new tagged release is published.
          </p>
          {sourceLabel && (
            <p className="mt-3 text-xs uppercase tracking-[0.18em] text-neon-green">
              You arrived {sourceLabel}. Pick your platform below.
            </p>
          )}
          <div className="mt-5 flex flex-wrap gap-3">
            <Link
              to="/"
              onClick={handleOpenAppClick}
              className="rounded-lg border border-neon-cyan/40 px-4 py-2 text-xs font-display uppercase tracking-[0.2em] text-neon-cyan transition hover:bg-neon-cyan/10"
            >
              Open App
            </Link>
            <a
              href={`https://github.com/${REPO}/releases`}
              target="_blank"
              rel="noreferrer"
              onClick={handleViewAllReleasesClick}
              className="rounded-lg border border-cyber-border px-4 py-2 text-xs font-display uppercase tracking-[0.2em] text-cyber-text transition hover:border-neon-pink/50 hover:text-neon-pink"
            >
              View All Releases
            </a>
          </div>
        </header>

        {loading && (
          <div className="rounded-2xl border border-cyber-border bg-cyber-surface/70 p-8 text-center">
            <div className="mb-4 inline-flex items-center gap-1">
              <div className="waveform-bar" />
              <div className="waveform-bar" />
              <div className="waveform-bar" />
              <div className="waveform-bar" />
            </div>
            <p className="text-sm uppercase tracking-[0.2em] text-cyber-muted">Syncing release feed...</p>
          </div>
        )}

        {!loading && error && (
          <div className="rounded-2xl border border-neon-red/40 bg-neon-red/10 p-6">
            <p className="text-sm text-neon-red">{error}</p>
            <button
              type="button"
              onClick={() => window.location.reload()}
              className="mt-4 rounded-lg border border-neon-red/40 px-4 py-2 text-xs font-display uppercase tracking-[0.2em] text-neon-red hover:bg-neon-red/10"
            >
              Retry
            </button>
          </div>
        )}

        {!loading && !error && (
          <section className="grid gap-4 sm:grid-cols-2">
            {targets.map((target) => {
              const available = Boolean(target.asset?.browser_download_url);

              return (
                <article
                  key={target.id}
                  className={`rounded-2xl border bg-cyber-surface/75 p-6 backdrop-blur-sm ${target.border}`}
                >
                  <p className="mb-2 text-xs uppercase tracking-[0.25em] text-cyber-muted">{target.subtitle}</p>
                  <h2 className={`mb-3 font-display text-2xl font-semibold ${target.accent}`}>{target.title}</h2>

                  <p className="mb-5 break-all text-xs text-cyber-muted">
                    {target.asset?.name || "No matching artifact found in latest release"}
                  </p>

                  {available ? (
                    <a
                      href={target.asset.browser_download_url}
                      onClick={() => handleDownloadClick(target)}
                      className="inline-block rounded-lg border border-cyber-border bg-cyber-panel px-4 py-2 text-xs font-display uppercase tracking-[0.2em] text-cyber-text transition hover:border-neon-cyan/60 hover:text-neon-cyan"
                    >
                      Download ({formatSize(target.asset.size)})
                    </a>
                  ) : (
                    <span className="inline-block rounded-lg border border-cyber-border/50 px-4 py-2 text-xs font-display uppercase tracking-[0.2em] text-cyber-muted">
                      Not available yet
                    </span>
                  )}
                </article>
              );
            })}
          </section>
        )}
      </div>
    </div>
  );
}
