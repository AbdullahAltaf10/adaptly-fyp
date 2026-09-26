/**
 * Create an account, and the profile row behind it.
 *
 * Two things have to happen and they can fail independently:
 *
 *   1. Firebase creates the credential (or one already exists, from Google)
 *   2. `POST /users/register` creates the profile the rest of the app reads
 *
 * A learner who completes step 1 and fails step 2 is in the worst state in the
 * app: signed in, with no profile, and nothing on screen explaining why. So
 * step 2 gets its own retry path rather than being fire-and-forget, and the
 * page detects that state on arrival — a Google user lands here *already*
 * authenticated, needing only step 2.
 *
 * `hr_admin` is deliberately not offered. The backend grants it only to an
 * address on its own allow-list and returns 403 to anyone else, so putting it
 * in the dropdown would be advertising something the server refuses.
 */

import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createUserWithEmailAndPassword, sendEmailVerification, updateProfile } from "firebase/auth";

import { auth } from "./firebase";
import { useAuth } from "./AuthContext";
import {
  REGISTRATION_MODES,
  collectErrors,
  describeAuthError,
  validateEmail,
  validateMode,
  validateName,
  validatePassword,
  validatePasswordConfirmation,
} from "./validation";
import api, { classifyError } from "../api/client";
import { Alert, Button, Card, CenteredPage, Field, Input, Select } from "../ui";

export default function RegisterPage() {
  const navigate = useNavigate();
  const { currentUser, refreshProfile } = useAuth();

  // Arriving already signed in means Google (or an earlier half-finished
  // attempt) handled step 1. Asking for a password again would be nonsense.
  const credentialExists = Boolean(currentUser);

  const [name, setName] = useState(currentUser?.displayName ?? "");
  const [email, setEmail] = useState(currentUser?.email ?? "");
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [mode, setMode] = useState("individual");

  const [errors, setErrors] = useState({});
  const [formError, setFormError] = useState(null);
  const [busy, setBusy] = useState(false);

  const createProfile = async (chosenMode) => {
    // `mode` is a query parameter on this endpoint, not a body field.
    await api.post(`/users/register?mode=${encodeURIComponent(chosenMode)}`);
  };

  const handleSubmit = async (event) => {
    event.preventDefault();
    setFormError(null);

    const found = collectErrors(
      credentialExists
        ? { name: validateName(name), mode: validateMode(mode) }
        : {
            name: validateName(name),
            email: validateEmail(email),
            password: validatePassword(password),
            confirmation: validatePasswordConfirmation(password, confirmation),
            mode: validateMode(mode),
          }
    );
    setErrors(found);
    if (Object.keys(found).length > 0) return;

    setBusy(true);
    try {
      if (!credentialExists) {
        const created = await createUserWithEmailAndPassword(auth, email.trim(), password);
        await updateProfile(created.user, { displayName: name.trim() });
        // Sent here rather than on the verification screen so it is already in
        // their inbox by the time they read the instruction to check it.
        await sendEmailVerification(created.user);
      }

      await createProfile(mode);
      await refreshProfile();
      navigate("/", { replace: true });
    } catch (error) {
      // A profile that already exists is not a failure - it means an earlier
      // attempt got further than it reported. Treat it as success rather than
      // stranding someone who is, in fact, fully registered.
      if (classifyError(error) === "bad_request" && /already exists/i.test(error?.response?.data?.detail ?? "")) {
        await refreshProfile();
        navigate("/", { replace: true });
        return;
      }
      setFormError(describeAuthError(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <CenteredPage>
      <Card
        title="Create your Adaptly account"
        subtitle={
          credentialExists
            ? "You are signed in. Just tell us how you will be using Adaptly."
            : "It takes a moment, and you can change these later."
        }
      >
        {formError && <Alert tone="error">{formError}</Alert>}

        <form onSubmit={handleSubmit} noValidate>
          <Field label="Your name" error={errors.name} required>
            {(aria) => (
              <Input
                {...aria}
                name="name"
                autoComplete="name"
                placeholder="Sara Ahmed"
                value={name}
                invalid={Boolean(errors.name)}
                onChange={(e) => setName(e.target.value)}
              />
            )}
          </Field>

          {!credentialExists && (
            <>
              <Field label="Email address" error={errors.email} required>
                {(aria) => (
                  <Input
                    {...aria}
                    type="email"
                    name="email"
                    autoComplete="email"
                    placeholder="you@example.com"
                    value={email}
                    invalid={Boolean(errors.email)}
                    onChange={(e) => setEmail(e.target.value)}
                  />
                )}
              </Field>

              <Field
                label="Password"
                error={errors.password}
                hint="At least 8 characters. Length matters more than symbols."
                required
              >
                {(aria) => (
                  <Input
                    {...aria}
                    type="password"
                    name="new-password"
                    autoComplete="new-password"
                    placeholder="Choose a password"
                    value={password}
                    invalid={Boolean(errors.password)}
                    onChange={(e) => setPassword(e.target.value)}
                  />
                )}
              </Field>

              <Field label="Confirm password" error={errors.confirmation} required>
                {(aria) => (
                  <Input
                    {...aria}
                    type="password"
                    name="confirm-password"
                    autoComplete="new-password"
                    placeholder="Type it again"
                    value={confirmation}
                    invalid={Boolean(errors.confirmation)}
                    onChange={(e) => setConfirmation(e.target.value)}
                  />
                )}
              </Field>
            </>
          )}

          <Field
            label="How will you use Adaptly?"
            error={errors.mode}
            hint="This decides which dashboard you land on."
            required
          >
            {(aria) => (
              <Select
                {...aria}
                name="mode"
                value={mode}
                invalid={Boolean(errors.mode)}
                onChange={(e) => setMode(e.target.value)}
              >
                {REGISTRATION_MODES.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label} — {option.hint}
                  </option>
                ))}
              </Select>
            )}
          </Field>

          <Button type="submit" className="w-full" busy={busy} busyLabel="Creating your account...">
            {credentialExists ? "Finish setting up" : "Create account"}
          </Button>
        </form>

        {!credentialExists && (
          <p className="mt-4 text-sm text-muted">
            Already have an account?{" "}
            <Link to="/signin" className="text-accent hover:underline">
              Sign in
            </Link>
          </p>
        )}
      </Card>
    </CenteredPage>
  );
}
