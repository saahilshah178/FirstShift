/**
 * Feature auto-discovery for the FirstShift frontend.
 *
 * Each `src/features/<name>/routes.js` exports:
 *   export const routes = [{ path, element }, ...];
 *   export const nav    = [{ label, path, order, side }, ...];
 *
 * `require.context` is a webpack built-in (CRA ships with webpack),
 * which is what makes this work *without* a shared registry file.
 *
 * By convention, caregiver-side routes have paths that begin with
 * `/c/:code` so the shell can mount them under a shared layout.
 */
const ctx = require.context("./features", true, /\/routes\.js$/);

const CAREGIVER_PREFIX = "/c/:code";

export function discoverFeatures() {
  const agencyRoutes = [];
  const caregiverRoutes = []; // { subpath: 'lessons'|'ask'|'', element }
  const nav = [];

  ctx.keys().forEach((key) => {
    try {
      const mod = ctx(key);
      if (Array.isArray(mod.routes)) {
        for (const r of mod.routes) {
          if (!r || typeof r.path !== "string" || !r.element) continue;
          if (r.path === CAREGIVER_PREFIX) {
            caregiverRoutes.push({ subpath: "", element: r.element });
          } else if (r.path.startsWith(CAREGIVER_PREFIX + "/")) {
            caregiverRoutes.push({
              subpath: r.path.slice(CAREGIVER_PREFIX.length + 1),
              element: r.element,
            });
          } else {
            agencyRoutes.push(r);
          }
        }
      }
      if (Array.isArray(mod.nav)) {
        for (const n of mod.nav) nav.push(n);
      }
    } catch (err) {
      // Fail-open: a broken feature must never break the app shell.
      // eslint-disable-next-line no-console
      console.error(`[featureRegistry] failed to load ${key}:`, err);
    }
  });

  nav.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  agencyRoutes.sort((a, b) => a.path.localeCompare(b.path));
  caregiverRoutes.sort((a, b) => a.subpath.localeCompare(b.subpath));
  return { agencyRoutes, caregiverRoutes, nav };
}

export function agencyNav(nav) {
  return nav.filter((n) => n.side === "agency");
}

export function caregiverNav(nav) {
  return nav.filter((n) => n.side === "caregiver");
}

/** Expand `/c/:code/...` in a nav path with a concrete code. */
export function withCode(path, code) {
  return path.replace(":code", encodeURIComponent(code));
}
