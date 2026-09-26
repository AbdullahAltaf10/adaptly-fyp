/**
 * The gate every signed-in route sits behind.
 *
 * There are more states here than "signed in or not", and collapsing them is
 * what produces the two worst bugs in an auth flow: bouncing a signed-in
 * learner to the sign-in page because their profile had not loaded yet, and
 * stranding a signed-in learner on a blank page because they have no profile
 * row.
 *
 *   loading            -> wait. Never redirect on a state you do not know yet.
 *   no Firebase user   -> /signin, remembering where they were going
 *   no profile row     -> /register (normal for a first Google sign-in)
 *   unverified email   -> /verify-email, except for providers that pre-verify
 *   backend unreachable-> say so, with a retry. Not a sign-in problem, and
 *                         sending them to /signin would suggest it was.
 *
 * `requireVerified` is opt-out so that forgetting it fails closed.
 */

import { Navigate, useLocation } from "react-router-dom";

import { useAuth } from "../auth/AuthContext";
import { Alert, Button, Card, CenteredPage, Spinner } from "../ui";

/**
 * Providers that have already confirmed the address themselves.
 *
 * Asking a Google user to verify an address Google just vouched for is a dead
 * end: Firebase marks them verified, so there is nothing for them to click.
 */
const PRE_VERIFIED_PROVIDERS = new Set(["google.com"]);

function signedInWithPreVerifiedProvider(user) {
  return (user?.providerData ?? []).some((p) => PRE_VERIFIED_PROVIDERS.has(p?.providerId));
}

export default function RequireAuth({ children, requireVerified = true }) {
  const { currentUser, profile, profileError, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <CenteredPage>
        <Spinner label="Checking your session..." />
      </CenteredPage>
    );
  }

  if (!currentUser) {
    return <Navigate to="/signin" replace state={{ from: location.pathname }} />;
  }

  if (profileError?.kind === "unreachable") {
    return (
      <CenteredPage>
        <Card title="Cannot reach the server">
          <Alert tone="error">
            You are signed in, but the Adaptly backend is not responding. This is usually the
            server still starting up.
          </Alert>
          <Button onClick={() => window.location.reload()}>Try again</Button>
        </Card>
      </CenteredPage>
    );
  }

  if (profileError?.kind === "no_profile" || (!profile && profileError)) {
    return <Navigate to="/register" replace />;
  }

  if (!profile) {
    return (
      <CenteredPage>
        <Spinner label="Loading your profile..." />
      </CenteredPage>
    );
  }

  if (
    requireVerified &&
    !currentUser.emailVerified &&
    !signedInWithPreVerifiedProvider(currentUser)
  ) {
    return <Navigate to="/verify-email" replace />;
  }

  return children;
}
