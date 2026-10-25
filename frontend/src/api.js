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

/* ---------------------------------------------------------------------
 * Stage 4-G: shared in-flight GET dedupe.
 *
 * Why this exists: React StrictMode (dev) mounts every effect twice. If
 * a component fires `api.get("/foo")` from a useEffect, both mounts hit
 * the network — the first-mount `AbortController.abort()` only cancels
 * the response delivery, not the request itself (it has already left
 * the client). The dedupe map collapses concurrent duplicate GETs into
 * a single underlying request; both callers resolve from the same
 * promise.
 *
 * Rules:
 *   - GETs only. POST/PUT/PATCH/DELETE pass through unchanged — side
 *     effects must never be deduped.
 *   - Key = `GET:${url}?${JSON.stringify(config.params ?? null)}`
 *     (method + URL + stringified query params; `config.headers` are
 *     role/content-type and don't change identity).
 *   - Entry is evicted on both resolve AND reject (finally()). A
 *     failing request doesn't poison the cache for the next retry.
 *   - The axios response interceptor above still fires for both callers
 *     because both hold the same promise — if one caller's handler
 *     mutates `response.data`, so does the other. In practice our
 *     fetchers only read, so this is safe.
 *   - Not an HTTP cache. Fresh requests are made as soon as the first
 *     resolves/rejects. Only *concurrent* duplicates are collapsed.
 * ------------------------------------------------------------------- */
const _inflight = new Map();

function _dedupeKey(url, config) {
  const params = config && config.params != null ? config.params : null;
  // JSON.stringify is stable enough for our params shape (flat scalars).
  // If a caller ever passes a non-serialisable param, swap this helper.
  return `GET:${url}?${JSON.stringify(params)}`;
}

const _origGet = api.get.bind(api);
api.get = function dedupedGet(url, config) {
  const key = _dedupeKey(url, config);
  const hit = _inflight.get(key);
  if (hit) return hit;
  const p = _origGet(url, config).finally(() => {
    // Only clear if we're still the owner — in the rare case a second
    // call started AFTER ours resolved, it won't be the same promise.
    if (_inflight.get(key) === p) _inflight.delete(key);
  });
  _inflight.set(key, p);
  return p;
};

// Exposed for the one-off StrictMode receipt — the tester or a dev
// console can read `window.__fsInflight.size` after a mount to assert
// no duplicate requests leaked. Not referenced elsewhere.
if (typeof window !== "undefined") {
  window.__fsInflight = _inflight;
}

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
