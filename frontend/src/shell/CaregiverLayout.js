import React, { createContext, useContext, useEffect, useState } from "react";
import { useParams, NavLink, Outlet, useNavigate } from "react-router-dom";
import { api } from "@/api";
import { caregiverNav, withCode } from "@/featureRegistry";

const CaregiverCtx = createContext(null);

export function useCaregiver() {
  const v = useContext(CaregiverCtx);
  if (!v) throw new Error("useCaregiver must be used inside CaregiverLayout");
  return v;
}

const FLAGS = { en: "🇺🇸", es: "🇪🇸", tl: "🇵🇭" };

export default function CaregiverLayout({ nav }) {
  const { code } = useParams();
  const navigate = useNavigate();
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    const ac = new AbortController();
    api
      .get(`/caregivers/by-code/${encodeURIComponent(code)}`, {
        signal: ac.signal,
      })
      .then((r) => setState({ status: "ok", data: r.data }))
      .catch((e) => {
        // Axios aborts surface as CanceledError (name) / ERR_CANCELED (code);
        // fetch would use AbortError. Treat all three the same.
        if (
          e?.name === "CanceledError" ||
          e?.name === "AbortError" ||
          e?.code === "ERR_CANCELED"
        ) {
          return;
        }
        const s = e?.response?.status;
        if (s === 404) {
          setState({ status: "404" });
        } else {
          setState({ status: "error", error: e?.message || "failed" });
        }
      });
    return () => ac.abort();
  }, [code]);

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
          <h1 className="text-2xl font-semibold">We can't find that code</h1>
          <p style={{ color: "var(--fs-muted)" }}>
            The link may be wrong, or the caregiver account was removed.
          </p>
          <button
            type="button"
            className="tap px-4 rounded-full font-ui text-sm"
            style={{
              background: "var(--fs-primary)",
              color: "var(--fs-primary-fg)",
            }}
            onClick={() => navigate("/")}
            data-testid="caregiver-back-home"
          >
            Back to agency
          </button>
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
              <span className="text-lg">
                {FLAGS[caregiver.language] ?? "🏳️"}
              </span>
              <h1
                data-testid="caregiver-name"
                className="text-lg font-semibold leading-tight"
              >
                {caregiver.name}
              </h1>
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
        <main className="flex-1 pb-24" data-testid="caregiver-main">
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
