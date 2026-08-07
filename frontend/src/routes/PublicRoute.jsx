import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function PublicRoute({ children }) {
  const { currentUser, profile, profileError, loading } = useAuth();
  const location = useLocation();

  if (loading) return <p style={{ padding: "2rem" }}>Loading...</p>;

  if (currentUser && profile) {
    if (profile.mode === "corporate") {
      return <Navigate to={profile.corporate_role === "hr_admin" ? "/hr" : "/employee"} />;
    }
    return <Navigate to="/learner" />;
  }

  // Signed in with Firebase but no profile yet — the normal state after a
  // first-time Google sign-in. Push them to registration instead of leaving
  // them on the login page, where they would just fail again.
  if (currentUser && profileError?.kind === "no_profile" && location.pathname !== "/register") {
    return <Navigate to="/register" />;
  }

  return children;
}
