import { createContext, useContext, useEffect, useState } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "../firebase/config";
import api, { classifyError } from "../api/client";

const AuthContext = createContext(null);

// The backend can take a few seconds to accept connections after it starts
// (module imports, first MongoDB Atlas handshake, first Firebase key fetch).
// Without retries, a page opened during that window failed once, left profile
// null forever, and the app sat on "Loading profile..." until a manual refresh.
const RETRY_DELAYS_MS = [500, 1000, 2000, 3000, 4000];

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null);
  const [profile, setProfile] = useState(null);
  const [profileError, setProfileError] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchProfile = async (user) => {
    if (!user) return;
    setProfileError(null);

    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
      try {
        const res = await api.get("/users/me");
        setProfile(res.data);
        setProfileError(null);
        return;
      } catch (err) {
        const kind = classifyError(err);

        // Signed in with Firebase but no profile row yet — this is the normal
        // state for a first-time Google sign-in. Retrying cannot help; the app
        // should send them to registration instead.
        if (kind === "not_found") {
          setProfile(null);
          setProfileError({ kind: "no_profile" });
          return;
        }

        // A bad or expired token will not fix itself by retrying either.
        if (kind === "unauthorized") {
          setProfile(null);
          setProfileError({ kind: "unauthorized" });
          return;
        }

        // Backend unreachable or erroring — this is the case worth retrying.
        if (attempt < RETRY_DELAYS_MS.length) {
          await sleep(RETRY_DELAYS_MS[attempt]);
          continue;
        }

        setProfile(null);
        setProfileError({
          kind: "unreachable",
          message: err.message || "Could not reach the server",
        });
      }
    }
  };

  useEffect(() => {
    const unsubscribe = onAuthStateChanged(auth, async (user) => {
      setCurrentUser(user);
      if (user) {
        await fetchProfile(user);
      } else {
        setProfile(null);
        setProfileError(null);
      }
      setLoading(false);
    });
    return unsubscribe;
  }, []);

  const refreshProfile = async () => {
    if (auth.currentUser) {
      await fetchProfile(auth.currentUser);
    }
  };

  const value = { currentUser, profile, profileError, loading, refreshProfile };

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
