/**
 * Feature auto-discovery for the FirstShift frontend.
 *
 * Each `src/features/<name>/routes.js` module must export:
 *   {
 *     routes: [{ path: string, element: ReactElement }],
 *     nav:    [{ label: string, path: string, order: number,
 *                side: 'agency' | 'caregiver' }]
 *   }
 *
 * `require.context` is a webpack-only feature (CRA ships with webpack),
 * which is what makes this work *without* a shared registry file.
 * No file in the app imports features by name — forks only add folders.
 */
const ctx = require.context("./features", true, /\/routes\.js$/);

export function discoverFeatures() {
  const routes = [];
  const nav = [];

  ctx.keys().forEach((key) => {
    try {
      const mod = ctx(key);
      if (Array.isArray(mod.routes)) {
        for (const r of mod.routes) {
          if (r && typeof r.path === "string" && r.element) {
            routes.push(r);
          }
        }
      }
      if (Array.isArray(mod.nav)) {
        for (const n of mod.nav) {
          nav.push(n);
        }
      }
    } catch (err) {
      // Fail-open: a broken feature must never break the app shell.
      // eslint-disable-next-line no-console
      console.error(`[featureRegistry] failed to load ${key}:`, err);
    }
  });

  nav.sort((a, b) => (a.order ?? 0) - (b.order ?? 0));
  routes.sort((a, b) => a.path.localeCompare(b.path));
  return { routes, nav };
}
