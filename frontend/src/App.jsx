/**
 * Routing for the whole application.
 *
 * This replaces the placeholder shell that rendered one screen and toggled to
 * a second with a boolean. Its own comment said `react-router-dom` was already
 * a dependency and unused, and that a real router was "worth a look if one is
 * wanted" - this is that change, and the rest of Module 1's frontend it was
 * standing in for.
 *
 * Route shape:
 *
 *   /signin  /register  /verify-email  /forgot-password    signed out
 *   /library /study /analytics /settings                   signed in
 *
 * The signed-in routes sit behind `RequireAuth`, which also handles the states
 * between "signed out" and "ready" - no profile row yet, unverified address,
 * backend unreachable - because each needs a different destination, and
 * collapsing them is what produces redirect loops.
 *
 * Accessibility settings are applied here rather than inside a page, so they
 * are in place before the first screen paints and survive navigation.
 */

import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";

import { useAuth } from "./auth/AuthContext";
import { useAccessibility } from "./auth/useAccessibility";
import ForgotPasswordPage from "./auth/ForgotPasswordPage";
import RegisterPage from "./auth/RegisterPage";
import SettingsPage from "./auth/SettingsPage";
import SignInPage from "./auth/SignInPage";
import VerifyEmailPage from "./auth/VerifyEmailPage";
import AppShell from "./routes/AppShell";
import RequireAuth from "./routes/RequireAuth";
import AnalyticsDashboardContainer from "./pages/AnalyticsDashboardContainer";
import StudySession from "./pages/StudySession";
import { Card, CenteredPage } from "./ui";

/** Keeps a signed-in learner off the signed-out screens. */
function SignedOutOnly({ children }) {
  const { currentUser, loading } = useAuth();
  if (loading) return children;
  return currentUser ? <Navigate to="/" replace /> : children;
}

function NotFound() {
  return (
    <CenteredPage>
      <Card title="Page not found" subtitle="That address does not match anything in Adaptly.">
        <a href="/" className="text-accent hover:underline">
          Go to the start
        </a>
      </Card>
    </CenteredPage>
  );
}

/**
 * Module 2's document list lands here next.
 *
 * A named placeholder rather than a missing route, so the nav item is not a
 * dead link and the gap is visible instead of silently absent.
 */
function LibraryPlaceholder() {
  return (
    <Card
      title="My documents"
      subtitle="Uploading and choosing a document is the next piece of Module 2's frontend."
    >
      <p className="text-muted">
        The six ingest endpoints already exist on the backend. Until this screen calls them, start
        a session from{" "}
        <a href="/study" className="text-accent hover:underline">
          Study session
        </a>
        .
      </p>
    </Card>
  );
}

export default function App() {
  const { profile } = useAuth();
  useAccessibility(profile);

  return (
    <BrowserRouter>
      <Routes>
        <Route
          path="/signin"
          element={
            <SignedOutOnly>
              <SignInPage />
            </SignedOutOnly>
          }
        />
        <Route
          path="/forgot-password"
          element={
            <SignedOutOnly>
              <ForgotPasswordPage />
            </SignedOutOnly>
          }
        />

        {/* Registration needs a signed-in Firebase user in the Google case and
            none in the email case, so it sits outside both guards. */}
        <Route path="/register" element={<RegisterPage />} />

        {/* The one signed-in screen that must NOT require a verified address,
            or it would redirect to itself forever. */}
        <Route
          path="/verify-email"
          element={
            <RequireAuth requireVerified={false}>
              <VerifyEmailPage />
            </RequireAuth>
          }
        />

        <Route
          element={
            <RequireAuth>
              <AppShell />
            </RequireAuth>
          }
        >
          <Route path="/" element={<Navigate to="/library" replace />} />
          <Route path="/library" element={<LibraryPlaceholder />} />
          <Route path="/study" element={<StudySession />} />
          <Route path="/analytics" element={<AnalyticsDashboardContainer />} />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
