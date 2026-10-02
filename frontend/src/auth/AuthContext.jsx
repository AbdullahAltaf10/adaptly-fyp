import { createContext, useContext, useEffect, useState } from "react";
import { onAuthStateChanged } from "firebase/auth";
import { auth } from "./firebase";
import api, { classifyError } from "../api/client";
import { getDeviceId } from "./deviceId";
import { deviceTrustStatus, twoFactorEnabled as fetchTwoFactorEnabled } from "./security";

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

  // Whether device-trust 2FA can run at all (Gmail configured on the
  // backend) versus whether THIS browser is trusted for THIS account. The
  // first is a feature flag - RequireAuth must never gate navigation behind
  // a code that can never arrive because nobody filled in GMAIL_ADDRESS yet.
  const [twoFactorEnabled, setTwoFactorEnabled] = useState(false);
  const [deviceTrusted, setDeviceTrusted] = useState(null);

  const refreshDeviceTrust = async () => {
    if (!auth.currentUser) return;
    try {
      setDeviceTrusted(await deviceTrustStatus(getDeviceId()));
    } catch {
      // Unreachable backend is handled by the profile fetch's own retry loop;
      // failing this quietly just means the gate stays closed until the next
      // check succeeds, not that navigation breaks.
    }
  };

  useEffect(() => {
    fetchTwoFactorEnabled()
      .then(setTwoFactorEnabled)
      .catch(() => setTwoFactorEnabled(false));
  }, []);

  const fetchProfile = async (user) => {
    if (!user) return;
    setProfileError(null);

    for (let attempt = 0; attempt <= RETRY_DELAYS_MS.length; attempt++) {
      try {
        const res = await api.get("/users/me");
        setProfile(res.data);
        setProfileError(null);
        refreshDeviceTrust();
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
        setDeviceTrusted(null);
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

  const value = {
    currentUser,
    profile,
    profileError,
    loading,
    refreshProfile,
    twoFactorEnabled,
    deviceTrusted,
    refreshDeviceTrust,
  };

  return (
    <AuthContext.Provider value={value}>
      {!loading && children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  return useContext(AuthContext);
}
