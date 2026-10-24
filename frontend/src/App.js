import React from "react";
import { BrowserRouter, Routes, Route, Link } from "react-router-dom";
import { discoverFeatures } from "@/featureRegistry";
import "@/App.css";

const { routes: featureRoutes, nav } = discoverFeatures();

function Shell({ children }) {
  return (
    <div className="min-h-screen bg-[color:var(--fs-bg)] text-[color:var(--fs-fg)]">
      <header className="border-b border-[color:var(--fs-border)]">
        <div className="mx-auto max-w-screen-sm px-5 py-4 flex items-center justify-between">
          <Link
            to="/"
            data-testid="brand-link"
            className="font-semibold tracking-tight text-lg"
          >
            FirstShift
          </Link>
          <span
            className="text-xs text-[color:var(--fs-muted)]"
            data-testid="phase-badge"
          >
            Phase 1 — Backbone
          </span>
        </div>
      </header>
      <main className="mx-auto max-w-screen-sm px-5 py-8">{children}</main>
    </div>
  );
}

function Home() {
  return (
    <div data-testid="home-root" className="space-y-6">
      <section>
        <h1 className="text-2xl font-semibold">Backbone online</h1>
        <p className="mt-2 text-sm text-[color:var(--fs-muted)]">
          No app shell yet. Feature folders are auto-discovered from{" "}
          <code className="font-mono text-xs">src/features/*/routes.js</code>{" "}
          via <code className="font-mono text-xs">require.context</code>. Fork a
          folder to add a feature — no central registry file to edit.
        </p>
      </section>

      <section data-testid="discovered-features">
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[color:var(--fs-muted)]">
          Discovered feature routes
        </h2>
        <ul className="mt-3 divide-y divide-[color:var(--fs-border)] border border-[color:var(--fs-border)] rounded-lg">
          {featureRoutes.map((r) => (
            <li key={r.path}>
              <Link
                to={r.path}
                data-testid={`feature-link-${r.path.replace(/^\//, "")}`}
                className="flex items-center justify-between px-4 py-3 min-h-[44px] active:bg-[color:var(--fs-accent)]"
              >
                <span className="font-mono text-sm">{r.path}</span>
                <span className="text-xs text-[color:var(--fs-muted)]">
                  open →
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-sm font-semibold uppercase tracking-wide text-[color:var(--fs-muted)]">
          Nav manifest
        </h2>
        <pre
          data-testid="nav-manifest"
          className="mt-3 text-xs bg-[color:var(--fs-accent)] p-3 rounded-lg overflow-x-auto"
        >
          {JSON.stringify(nav, null, 2)}
        </pre>
      </section>
    </div>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Shell>
        <Routes>
          <Route path="/" element={<Home />} />
          {featureRoutes.map((r) => (
            <Route key={r.path} path={r.path} element={r.element} />
          ))}
          <Route
            path="*"
            element={
              <div data-testid="not-found" className="py-10 text-center">
                <p className="text-sm text-[color:var(--fs-muted)]">
                  Not found.
                </p>
                <Link
                  to="/"
                  className="mt-3 inline-block underline text-sm"
                  data-testid="home-link"
                >
                  Back to home
                </Link>
              </div>
            }
          />
        </Routes>
      </Shell>
    </BrowserRouter>
  );
}
