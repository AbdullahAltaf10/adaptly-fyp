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

import AnalyticsDashboard from "./pages/AnalyticsDashboard";
import { useAuth } from "./auth/AuthContext";
import { auth, googleProvider } from "./auth/firebase";
import ComplianceReportPage from "./pages/ComplianceReportPage";
import HrComplianceReportsPage from "./pages/HrComplianceReportsPage";
import StudySession from "./pages/StudySession";

// Module 8 (Issue #81) and Module 10 (Issue #81) each added a view toggle on
// separate branches (PR #86 for the analytics dashboard, this stack for the
// compliance report views) -- this file still has no router, and introducing
// one isn't either issue's call to make unilaterally, so both toggles are
// reconciled here into one plain multi-way view switch. `react-router-dom`
// is already a dependency but unused anywhere in the app -- worth a look if
// a real router is wanted instead.
const VIEW_STUDY_SESSION = "study_session";
const VIEW_ANALYTICS_DASHBOARD = "analytics_dashboard";
const VIEW_COMPLIANCE_REPORT = "compliance_report";
const VIEW_HR_COMPLIANCE_REPORTS = "hr_compliance_reports";

export default function App() {
  const { currentUser, profile, profileError, refreshProfile } = useAuth();
  const [signInError, setSignInError] = useState(null);
  const [view, setView] = useState(VIEW_STUDY_SESSION);

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
        <nav style={{ display: "flex", gap: "0.5rem", alignItems: "center" }}>
          <h1 style={{ fontSize: "1.3rem", margin: 0 }}>Adaptly</h1>
          <button onClick={() => setView(VIEW_STUDY_SESSION)} style={{ marginLeft: "1rem" }}>
            Study session
          </button>
          <button onClick={() => setView(VIEW_ANALYTICS_DASHBOARD)}>
            Analytics dashboard
          </button>
          <button onClick={() => setView(VIEW_COMPLIANCE_REPORT)}>
            Compliance report
          </button>
          {profile?.corporate_role === "hr_admin" && (
            <button onClick={() => setView(VIEW_HR_COMPLIANCE_REPORTS)}>
              HR: compliance reports
            </button>
          )}
        </nav>
        <span style={{ fontSize: "0.85rem", color: "#666" }}>
          {profile?.name || currentUser.email}
          <button onClick={() => signOut(auth)} style={{ marginLeft: "0.75rem" }}>
            Sign out
          </button>
        </span>
      </header>

      {view === VIEW_STUDY_SESSION && (
        <StudySession
          highContrast={profile?.accessibility_settings?.contrast === "high"}
        />
      )}
      {/* No completed-session id is threaded up from StudySession to App yet
          (a separate, larger change), so this shows representative mock
          data rather than nothing -- the same mock default AnalyticsDashboard
          already falls back to when no real fetcher is given. Wiring the
          real just-finished session's id through is follow-up work. */}
      {view === VIEW_ANALYTICS_DASHBOARD && (
        <AnalyticsDashboard session={{ sessionId: "demo-session", status: "completed" }} />
      )}
      {/* Same known limitation as the analytics dashboard above --
          ComplianceReportPage's default fetcher renders representative data
          instead of nothing until a real session id is threaded through. */}
      {view === VIEW_COMPLIANCE_REPORT && (
        <ComplianceReportPage sessionId="demo-session" />
      )}
      {view === VIEW_HR_COMPLIANCE_REPORTS && <HrComplianceReportsPage />}
    </main>
  );
}
