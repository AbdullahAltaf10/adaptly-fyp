/**
 * Minimal application shell.
 *
 * This exists so the Module 3 webcam-to-engagement pipeline can be run and
 * reviewed end to end. It is deliberately thin: sign in, then the study
 * session. The full learner-facing frontend - registration, role-based
 * dashboards, accessibility settings, protected routing - belongs to the
 * Module 1 frontend migration and will replace this file rather than build on
 * it. Nothing here should be treated as a decision about the app's navigation.
 */

import { signInWithPopup, signOut } from "firebase/auth";
import { useState } from "react";

import { useAuth } from "./auth/AuthContext";
import { auth, googleProvider } from "./auth/firebase";
import StudySession from "./pages/StudySession";

export default function App() {
  const { currentUser, profile, profileError, refreshProfile } = useAuth();
  const [signInError, setSignInError] = useState(null);

  const handleSignIn = async () => {
    setSignInError(null);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      setSignInError(err.message);
    }
  };

  if (!currentUser) {
    return (
      <main style={{ maxWidth: "420px", margin: "10vh auto", textAlign: "center" }}>
        <h1>Adaptly</h1>
        <p>Sign in to start a study session.</p>
        <button onClick={handleSignIn}>Continue with Google</button>
        {signInError && <p style={{ color: "#b3261e" }}>{signInError}</p>}
      </main>
    );
  }

  // Signed in with Firebase but no profile in the database. Normal for a
  // first-time sign-in; registration is Module 1 frontend work, so for now the
  // situation is reported rather than handled.
  if (profileError?.kind === "no_profile") {
    return (
      <main style={{ maxWidth: "520px", margin: "10vh auto", textAlign: "center" }}>
        <h1>Adaptly</h1>
        <p>
          Signed in as {currentUser.email}, but this account has no profile yet.
          Register through <code>POST /users/register</code> until the Module 1
          registration screen exists.
        </p>
        <button onClick={refreshProfile}>Check again</button>
        <button onClick={() => signOut(auth)} style={{ marginLeft: "0.5rem" }}>
          Sign out
        </button>
      </main>
    );
  }

  if (profileError?.kind === "unreachable") {
    return (
      <main style={{ maxWidth: "520px", margin: "10vh auto", textAlign: "center" }}>
        <h1>Adaptly</h1>
        <p style={{ color: "#b3261e" }}>
          Could not reach the backend. Start it with{" "}
          <code>uvicorn app.main:app --reload</code> from <code>backend/</code>,
          then try again.
        </p>
        <button onClick={refreshProfile}>Retry</button>
      </main>
    );
  }

  return (
    <main>
      <header
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: "1rem",
        }}
      >
        <h1 style={{ fontSize: "1.3rem", margin: 0 }}>Study session</h1>
        <span style={{ fontSize: "0.85rem", color: "#666" }}>
          {profile?.name || currentUser.email}
          <button onClick={() => signOut(auth)} style={{ marginLeft: "0.75rem" }}>
            Sign out
          </button>
        </span>
      </header>

      <StudySession
        highContrast={profile?.accessibility_settings?.contrast === "high"}
      />
    </main>
  );
}
