import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { createUserWithEmailAndPassword, signInWithPopup } from "firebase/auth";
import { auth, googleProvider } from "../firebase/config";
import { useAuth } from "../context/AuthContext";
import api from "../api/client";

export default function Register() {
  const navigate = useNavigate();
  const { refreshProfile } = useAuth();
  const [mode, setMode] = useState("learner");
  const [role, setRole] = useState("employee");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");

  const routeByMode = () => {
    if (mode === "learner") navigate("/learner");
    else if (role === "hr_admin") navigate("/hr");
    else navigate("/employee");
  };

  const saveProfileToBackend = async () => {
    try {
      await api.post("/users/register", {}, {
        params: mode === "corporate" ? { mode, role } : { mode },
      });
    } catch (err) {
      // 400 here means a profile already exists for this account. That is not
      // a failure from the user's point of view — refreshing the profile below
      // will pick it up and route them onward.
      if (err.response?.status !== 400) throw err;
    }
    await refreshProfile();
  };

  const handleRegister = async (e) => {
    e.preventDefault();
    setError("");
    try {
      await createUserWithEmailAndPassword(auth, email, password);
      await saveProfileToBackend();
      routeByMode();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleGoogleSignup = async (e) => {
    setError("");
    try {
      await signInWithPopup(auth, googleProvider);
      await saveProfileToBackend();
      routeByMode();
    } catch (err) {
      setError(err.message);
    }
  };

  return (
    <div style={{ maxWidth: 400, margin: "3rem auto", fontFamily: "sans-serif" }}>
      <h2>Register</h2>

      <div style={{ marginBottom: "1rem" }}>
        <label>
          <input type="radio" checked={mode === "learner"} onChange={() => setMode("learner")} />
          Learner Mode
        </label>
        <label style={{ marginLeft: "1rem" }}>
          <input type="radio" checked={mode === "corporate"} onChange={() => setMode("corporate")} />
          Corporate Mode
        </label>
      </div>

      {mode === "corporate" && (
        <div style={{ marginBottom: "1rem" }}>
          <label>
            <input type="radio" checked={role === "employee"} onChange={() => setRole("employee")} />
            Employee
          </label>
          <label style={{ marginLeft: "1rem" }}>
            <input type="radio" checked={role === "hr_admin"} onChange={() => setRole("hr_admin")} />
            HR Admin
          </label>
        </div>
      )}

      <form onSubmit={handleRegister}>
        <input
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          style={{ display: "block", width: "100%", marginBottom: "0.5rem", padding: "0.5rem" }}
        />
        <input
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          style={{ display: "block", width: "100%", marginBottom: "0.5rem", padding: "0.5rem" }}
        />
        <button type="submit" style={{ width: "100%", padding: "0.6rem" }}>
          Register
        </button>
      </form>

      <button onClick={handleGoogleSignup} style={{ width: "100%", padding: "0.6rem", marginTop: "0.5rem" }}>
        Sign up with Google
      </button>

      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}