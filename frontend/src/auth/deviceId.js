/**
 * A random identifier for THIS browser, not this person or this session.
 *
 * Generated once and kept in localStorage. There is no hardware fingerprinting
 * here on purpose - clearing site data or opening a different browser looking
 * like "a new device" is the honest, expected behaviour, not a bug to work
 * around. The backend only ever sees this string; it cannot be turned back
 * into anything identifying on its own.
 */
const STORAGE_KEY = "adaptly_device_id";

export function getDeviceId() {
  try {
    const existing = window.localStorage.getItem(STORAGE_KEY);
    if (existing) return existing;

    const generated = crypto.randomUUID();
    window.localStorage.setItem(STORAGE_KEY, generated);
    return generated;
  } catch {
    // Private browsing / blocked storage: fall back to a per-load id. Every
    // sign-in will re-challenge, which is safe, just less convenient.
    return crypto.randomUUID();
  }
}
