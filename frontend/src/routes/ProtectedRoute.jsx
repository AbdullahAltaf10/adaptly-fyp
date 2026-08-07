import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function ProtectedRoute({ children, allowedMode, allowedRole }) {
  const { currentUser, profile, profileError, loading, refreshProfile } = useAuth();

  if (loading) return <p style={{ padding: "2rem" }}>Loading...</p>;
  if (!currentUser) return <Navigate to="/login" />;

  if (!profile) {
    // Signed in but never registered — send them to finish signing up rather
    // than leaving them on a screen with no way forward.
    if (profileError?.kind === "no_profile") return <Navigate to="/register" />;

    // Token rejected: treat as signed out.
    if (profileError?.kind === "unauthorized") return <Navigate to="/login" />;

    // Backend unreachable even after retries. This used to hang forever on
    // "Loading profile..." with no explanation and no way to recover.
    if (profileError?.kind === "unreachable") {
      return (
        <div style={{ padding: "2rem" }}>
          <h3>Can't reach the server</h3>
          <p>
            The backend isn't responding. If you just started it, give it a few
            seconds and try again.
          </p>
          <p style={{ color: "#666", fontSize: "0.85em" }}>{profileError.message}</p>
          <button onClick={refreshProfile}>Try again</button>
        </div>
      );
    }

    return <p style={{ padding: "2rem" }}>Loading profile...</p>;
  }

  if (allowedMode && profile.mode !== allowedMode) return <Navigate to="/login" />;
  if (allowedRole && profile.corporate_role !== allowedRole) return <Navigate to="/login" />;

  return children;
}
