import axios from "axios";
import { auth } from "../firebase/config";

/**
 * Single place that knows where the backend lives and how to authenticate.
 *
 * Configure with VITE_API_URL in frontend/.env. The fallback is the local dev
 * backend so the app still runs with no .env present — that default is the one
 * intentional hardcode here, and it exists only so a fresh clone works.
 */
export const API_BASE_URL = import.meta.env.VITE_API_URL || "http://127.0.0.1:8000";

const api = axios.create({
  baseURL: API_BASE_URL,
  // Short enough that a backend which is still starting fails fast and lets the
  // caller retry, rather than leaving the UI hanging indefinitely.
  timeout: 20000,
});

// Attach the Firebase ID token to every request, so no page has to remember to.
// getIdToken() serves a cached token and refreshes it automatically when it is
// close to expiring, so this is cheap to call on every request.
api.interceptors.request.use(async (config) => {
  const user = auth.currentUser;
  if (user) {
    config.headers.Authorization = `Bearer ${await user.getIdToken()}`;
  }
  return config;
});

/**
 * Classifies a failed request so callers can tell "you have no profile yet"
 * apart from "the backend is not answering". Previously every failure looked
 * identical, which made a CORS problem surface as an unexplained hang.
 */
export function classifyError(err) {
  const status = err.response?.status;
  if (status === 404) return "not_found";
  if (status === 401 || status === 403) return "unauthorized";
  if (!err.response) return "unreachable"; // no response at all: down, CORS, timeout
  return "server_error";
}

export default api;
