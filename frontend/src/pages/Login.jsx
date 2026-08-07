import { useState } from "react";
import { signInWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { auth, googleProvider } from "../firebase/config";

export default function Login() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  // No profile fetch or navigation here on purpose. Signing in updates
  // AuthContext, and PublicRoute then redirects: to the right dashboard if a
  // profile exists, or to /register if this account has never registered.
  // The old version fetched /users/me itself and surfaced the 404 for a
  // first-time Google user as a raw error, stranding them on this page.

  const handleLogin = async (e) => {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      await signInWithEmailAndPassword(auth, email, password);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleGoogleLogin = async () => {
    setError("");
    setBusy(true);
    try {
      await signInWithPopup(auth, googleProvider);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "3rem auto", fontFamily: "sans-serif" }}>
      <h2>Login</h2>
      <form onSubmit={handleLogin}>
        <input type="email" placeholder="Email" value={email} onChange={(e) => setEmail(e.target.value)} required
          style={{ display: "block", width: "100%", marginBottom: "0.5rem", padding: "0.5rem" }} />
        <input type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} required
          style={{ display: "block", width: "100%", marginBottom: "0.5rem", padding: "0.5rem" }} />
        <button type="submit" disabled={busy} style={{ width: "100%", padding: "0.6rem" }}>
          {busy ? "Signing in..." : "Login"}
        </button>
      </form>
      <button onClick={handleGoogleLogin} disabled={busy} style={{ width: "100%", padding: "0.6rem", marginTop: "0.5rem" }}>
        Sign in with Google
      </button>
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}
