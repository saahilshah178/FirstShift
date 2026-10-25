import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "";
export const API = `${BACKEND_URL}/api`;

const ROLE_KEY = "firstshift.agency_role";

/**
 * Agency role from localStorage. The agency app writes this when the
 * role switch changes; the caregiver side is role-independent (we still
 * send the header, but caregiver endpoints have no gate on the server).
 *
 * See `backend/roles.py` + `docs/merge/mvp-hardening.md` → Role matrix.
 */
export function currentRole() {
  try {
    return localStorage.getItem(ROLE_KEY) || "Care Manager";
  } catch {
    return "Care Manager";
  }
}

export const api = axios.create({
  baseURL: API,
  // Media URLs are relative; the frontend prepends BACKEND_URL.
});

// Attach the role header on every outbound request. Backend ignores it
// on open (read / caregiver) endpoints and enforces it on gated ones.
api.interceptors.request.use((config) => {
  const role = currentRole();
  config.headers = config.headers || {};
  // Only set when absent so a caller can override explicitly (useful in
  // tests + the Batch-3 manual role matrix in merge notes).
  if (config.headers["X-Firstshift-Role"] === undefined) {
    config.headers["X-Firstshift-Role"] = role;
  }
  return config;
});

// 403 interceptor — the UI almost always hides the button a role can't
// use, but if the server rejects anyway (stale role switch, forged
// header via dev tools, etc.) surface a friendly toast instead of a
// silent failure. `onForbidden` is attached by the shell at app boot.
let _onForbidden = null;
export function setForbiddenHandler(fn) {
  _onForbidden = typeof fn === "function" ? fn : null;
}

api.interceptors.response.use(
  (resp) => resp,
  (err) => {
    const status = err?.response?.status;
    const detail = err?.response?.data?.detail;
    if (status === 403 && detail && typeof detail === "object") {
      const reason = detail.reason;
      if (reason === "role_required" || reason === "role_not_allowed") {
        if (_onForbidden) {
          try {
            _onForbidden({
              reason,
              role: detail.role,
              allowed: detail.allowed || [],
            });
          } catch (e) {
            // never let a toast handler crash the fetch chain
            // eslint-disable-next-line no-console
            console.error("[api] onForbidden handler threw", e);
          }
        }
      }
    }
    return Promise.reject(err);
  },
);

/** Build a full URL from a relative `/api/...` path returned by the backend. */
export function absoluteUrl(relativePath) {
  if (!relativePath) return relativePath;
  if (/^https?:\/\//i.test(relativePath)) return relativePath;
  return `${BACKEND_URL}${relativePath}`;
}
