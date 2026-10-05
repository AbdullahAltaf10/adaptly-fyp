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
 *   /signin  /register  /verify-email  /verify-device  /forgot-password    signed out
 *   /  /library /library/new /study /analytics /progress /settings   signed in
 *   /compliance                                            signed in, corporate
 *   /hr/compliance                                         signed in, hr_admin
 *
 * "/" is the dashboard home screen (`DashboardPage`), not a redirect - it used
 * to bounce straight to /library, which meant no page ever showed a learner
 * anything about their own progress before they picked a document.
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
import VerifyDevicePage from "./auth/VerifyDevicePage";
import VerifyEmailPage from "./auth/VerifyEmailPage";
import AppShell from "./routes/AppShell";
import RequireAuth from "./routes/RequireAuth";
import AnalyticsDashboardContainer from "./pages/AnalyticsDashboardContainer";
import ComplianceReportPage from "./pages/ComplianceReportPage";
import DashboardPage from "./pages/DashboardPage";
import HrComplianceReportsPage from "./pages/HrComplianceReportsPage";
import ProgressPage from "./pages/ProgressPage";
import LibraryPage from "./content/LibraryPage";
import UploadPage from "./content/UploadPage";
import StudyRoute from "./routes/StudyRoute";
import { Card, CenteredPage } from "./ui";

/** Keeps a signed-in learner off the signed-out screens. */
function SignedOutOnly({ children }) {
  const { currentUser, loading } = useAuth();
  if (loading) return children;
  return currentUser ? <Navigate to="/" replace /> : children;
}

/**
 * Module 10's HR list is for `hr_admin` only. The backend enforces this
 * (`require_hr_admin` on `GET /api/compliance/reports`); this only keeps a
 * non-HR learner from landing on a page that would just show an error.
 */
function HrAdminOnly({ children }) {
  const { profile } = useAuth();
  return profile?.corporate_role === "hr_admin" ? children : <Navigate to="/compliance" replace />;
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

        {/* Same reasoning as /verify-email: must not require the very thing
            it exists to establish, or it would redirect to itself forever. */}
        <Route
          path="/verify-device"
          element={
            <RequireAuth requireDeviceTrust={false}>
              <VerifyDevicePage />
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
          <Route path="/" element={<DashboardPage />} />
          <Route path="/library" element={<LibraryPage />} />
          <Route path="/library/new" element={<UploadPage />} />
          <Route path="/study" element={<StudyRoute />} />
          <Route path="/analytics" element={<AnalyticsDashboardContainer />} />
          <Route path="/progress" element={<ProgressPage />} />
          <Route path="/compliance" element={<ComplianceReportPage />} />
          <Route
            path="/hr/compliance"
            element={
              <HrAdminOnly>
                <HrComplianceReportsPage />
              </HrAdminOnly>
            }
          />
          <Route path="/settings" element={<SettingsPage />} />
        </Route>

        <Route path="*" element={<NotFound />} />
      </Routes>
    </BrowserRouter>
  );
}
