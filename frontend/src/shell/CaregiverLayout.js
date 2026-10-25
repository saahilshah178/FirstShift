import React, { createContext, useContext, useEffect, useState } from "react";
import { useParams, NavLink, Outlet, useNavigate, useLocation } from "react-router-dom";
import { api } from "@/api";
import { caregiverNav, withCode } from "@/featureRegistry";

const CaregiverCtx = createContext(null);

export function useCaregiver() {
  const v = useContext(CaregiverCtx);
  if (!v) throw new Error("useCaregiver must be used inside CaregiverLayout");
  return v;
}

const LANG_NAMES = { en: "English", es: "Español", tl: "Tagalog" };

export default function CaregiverLayout({ nav }) {
  const { code } = useParams();
  const navigate = useNavigate();
  const location = useLocation();
  const [state, setState] = useState({ status: "loading" });

  // Canonical access codes are uppercase (seed enforces [A-HJ-KM-NP-Z2-9]).
  // Normalise anything lowercase a user may have hand-typed by redirecting
  // in place. Done BEFORE the by-code lookup so the backend sees the
  // canonical form and the URL you share works both ways.
  const upperCode = (code || "").toUpperCase();
  const needsUpperRedirect = code && code !== upperCode;
  useEffect(() => {
    if (needsUpperRedirect) {
      // Preserve the sub-path (/chat, /practice, …) after /c/<code>.
      const suffix = location.pathname.slice(`/c/${code}`.length);
      navigate(`/c/${upperCode}${suffix}${location.search}${location.hash}`, {
        replace: true,
      });
    }
  }, [needsUpperRedirect, code, upperCode, navigate, location.pathname, location.search, location.hash]);

  useEffect(() => {
    if (needsUpperRedirect) return undefined;
    // Stage 4-G: shared GET dedupe in api.js collapses the StrictMode
    // double-mount into one request. No local AbortController — mixing
    // signal-based cancellation with the shared promise cache rejects
    // mount-2's handler with CanceledError and the state never advances.
    api
      .get(`/caregivers/by-code/${encodeURIComponent(upperCode)}`)
      .then((r) => setState({ status: "ok", data: r.data }))
      .catch((e) => {
        const s = e?.response?.status;
        if (s === 404) {
          setState({ status: "404" });
        } else {
          setState({ status: "error", error: e?.message || "failed" });
        }
      });
  }, [upperCode, needsUpperRedirect]);

  if (state.status === "loading") {
    return (
      <div
        className="fs-frame"
        data-side="caregiver"
        data-testid="caregiver-loading"
      >
        <div className="flex-1 flex items-center justify-center">
          <p style={{ color: "var(--fs-muted)" }}>Opening…</p>
        </div>
      </div>
    );
  }

  if (state.status === "404") {
    return (
      <div
        className="fs-frame"
        data-side="caregiver"
        data-testid="caregiver-404"
      >
        <div className="flex-1 flex flex-col items-center justify-center text-center px-8 gap-3">
          <h1 className="text-2xl font-semibold">Code not found</h1>
          <p style={{ color: "var(--fs-muted)" }}>
            Please check your link or contact your coordinator.
          </p>
          {/* Stage 4-F: no "Back to agency" button — caregivers never
              see agency surfaces. Agency staff who hit this via a bad
              code in the picker can use the browser back button. */}
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div
        className="fs-frame"
        data-side="caregiver"
        data-testid="caregiver-error"
      >
        <div className="flex-1 flex items-center justify-center">
          <p style={{ color: "var(--fs-fail)" }}>Error: {state.error}</p>
        </div>
      </div>
    );
  }

  const { caregiver, agency } = state.data;
  const items = caregiverNav(nav);
  return (
    <CaregiverCtx.Provider value={{ caregiver, agency, code }}>
      <div
        className="fs-frame"
        data-side="caregiver"
        data-testid="caregiver-shell"
      >
        <header
          className="sticky top-0 z-20 border-b px-5 py-3 flex items-center justify-between"
          style={{
            borderColor: "var(--fs-border)",
            background: "var(--fs-surface)",
          }}
        >
          <div>
            <div className="flex items-center gap-2">
              <h1
                data-testid="caregiver-name"
                className="text-lg font-semibold leading-tight"
              >
                {caregiver.name}
              </h1>
              <span
                data-testid="caregiver-language"
                className="font-ui text-[11px] px-2 py-0.5 rounded-full"
                style={{
                  color: "var(--fs-muted)",
                  background: "var(--fs-accent)",
                }}
              >
                {LANG_NAMES[caregiver.language] ?? caregiver.language}
              </span>
            </div>
            <p
              className="text-xs font-ui"
              style={{ color: "var(--fs-muted)" }}
            >
              {agency?.name}
            </p>
          </div>
          <code
            data-testid="caregiver-code"
            className="font-ui text-xs tracking-widest px-2 py-1 rounded"
            style={{ background: "var(--fs-accent)" }}
          >
            {code}
          </code>
        </header>
        <main
          className="flex-1 pb-14 overflow-y-auto"
          data-testid="caregiver-main"
        >
          <Outlet />
        </main>
        <nav
          className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full border-t"
          data-testid="caregiver-nav"
          style={{
            maxWidth: "var(--fs-max-w)",
            background: "var(--fs-surface)",
            borderColor: "var(--fs-border)",
          }}
        >
          <ul className="grid grid-cols-4 font-ui text-xs">
            {items.map((n) => {
              const to = withCode(n.path, code);
              return (
                <li key={n.path}>
                  <NavLink
                    end
                    to={to}
                    data-testid={`caregiver-nav-${n.label.toLowerCase()}`}
                    className={({ isActive }) =>
                      [
                        "flex items-center justify-center h-14",
                        isActive
                          ? "text-[color:var(--fs-primary)] font-semibold"
                          : "text-[color:var(--fs-muted)]",
                      ].join(" ")
                    }
                  >
                    {n.label}
                  </NavLink>
                </li>
              );
            })}
          </ul>
        </nav>
      </div>
    </CaregiverCtx.Provider>
  );
}
