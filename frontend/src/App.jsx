import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ThemeProvider } from "./context/ThemeContext";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import HomePage from "./pages/HomePage";
import InvitePage from "./pages/InvitePage";
import ForgotPasswordPage from "./pages/ForgotPasswordPage";
import ResetPasswordPage from "./pages/ResetPasswordPage";
import DownloadPage from "./pages/DownloadPage";
import { buildAuthLink, getAuthRedirect, getLocationPath } from "./utils/authRedirect";
import SessionStatus from "./components/SessionStatus";
import DesktopLinkBridge from "./components/DesktopLinkBridge";

function ProtectedRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
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

  return user ? children :
    <Navigate to={buildAuthLink("/login", getLocationPath(location))} replace />;
}

function GuestRoute({ children }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return null;
  return user ? <Navigate to={getAuthRedirect(location.search)} replace /> : children;
}

export default function App() {
  return (
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <DesktopLinkBridge />
          <SessionStatus>
          <Routes>
            <Route
              path="/login"
              element={<GuestRoute><LoginPage /></GuestRoute>}
            />
            <Route
              path="/register"
              element={<GuestRoute><RegisterPage /></GuestRoute>}
            />
            <Route
              path="/forgot-password"
              element={<GuestRoute><ForgotPasswordPage /></GuestRoute>}
            />
            <Route
              path="/reset-password"
              element={<GuestRoute><ResetPasswordPage /></GuestRoute>}
            />
            <Route
              path="/invite/:code"
              element={<InvitePage />}
            />
            <Route
              path="/download"
              element={<DownloadPage />}
            />
            <Route
              path="/"
              element={<ProtectedRoute><HomePage /></ProtectedRoute>}
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
          </SessionStatus>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  );
}
