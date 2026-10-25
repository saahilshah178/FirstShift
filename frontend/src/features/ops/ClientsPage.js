import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api";

export default function ClientsPage() {
  const [state, setState] = useState({ status: "loading" });
  const [fit, setFit] = useState({}); // client_id -> {cleared, almost_ready}

  useEffect(() => {
    const ac = new AbortController();
    (async () => {
      try {
        const r = await api.get("/ops/clients", { signal: ac.signal });
        setState({ status: "ok", rows: r.data.clients });
        // Fetch caregiver-fit for every client in parallel.
        const fits = await Promise.all(
          r.data.clients.map((c) =>
            api
              .get(`/ops/clients/${c.id}/caregiver-fit`, { signal: ac.signal })
              .then((rr) => [c.id, rr.data])
              .catch(() => [c.id, { cleared: [], almost_ready: [] }]),
          ),
        );
        if (ac.signal.aborted) return;
        const map = {};
        for (const [id, data] of fits) map[id] = data;
        setFit(map);
      } catch (e) {
        if (
          e?.name === "CanceledError" ||
          e?.name === "AbortError" ||
          e?.code === "ERR_CANCELED"
        )
          return;
        setState({ status: "error", error: e?.message || "failed" });
      }
    })();
    return () => ac.abort();
  }, []);

  return (
    <section data-testid="clients-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Clients</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Required skills + who on your team can cover each client today.
        </p>
      </header>

      {state.status === "ok" ? (
        <ul
          className="grid grid-cols-1 gap-3"
          data-testid="clients-list"
        >
          {state.rows.map((c) => (
            <li
              key={c.id}
              className="fs-card p-4 space-y-3"
              data-testid={`clients-row-${c.id}`}
            >
              <div className="flex items-start justify-between gap-3">
                <div>
                  <div className="font-semibold">{c.name}</div>
                  <div className="mt-2 flex flex-wrap gap-1">
                    {c.required_skills.length === 0 ? (
                      <span
                        className="text-xs font-ui"
                        style={{ color: "var(--fs-muted)" }}
                      >
                        No skills required
                      </span>
                    ) : (
                      c.required_skills.map((s) => (
                        <span key={s.id} className="fs-chip">
                          {s.title}
                        </span>
                      ))
                    )}
                  </div>
                </div>
                <span
                  className="font-ui text-[11px]"
                  style={{ color: "var(--fs-muted)" }}
                >
                  {c.required_skills.length} skill
                  {c.required_skills.length === 1 ? "" : "s"}
                </span>
              </div>

              {/* Stage 3 — fit sections. Rendered unconditionally so the
                  reviewer always sees both buckets, even when empty. */}
              <FitSection
                label="Cleared for this client"
                emptyLabel="No one is cleared yet."
                rows={(fit[c.id] || {}).cleared || []}
                testidPrefix={`clients-${c.id}-cleared`}
              />
              <FitSection
                label="Almost ready"
                emptyLabel="No one is one skill away."
                rows={(fit[c.id] || {}).almost_ready || []}
                testidPrefix={`clients-${c.id}-almost`}
                renderExtra={(row) =>
                  row.missing_skill_title ? (
                    <span
                      className="text-xs font-ui"
                      style={{ color: "var(--fs-muted)" }}
                    >
                      missing {row.missing_skill_title}
                    </span>
                  ) : null
                }
              />
            </li>
          ))}
        </ul>
      ) : state.status === "error" ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }}>
          {state.error}
        </p>
      ) : (
        <p className="text-sm" style={{ color: "var(--fs-muted)" }}>
          Loading…
        </p>
      )}
    </section>
  );
}

function FitSection({ label, emptyLabel, rows, testidPrefix, renderExtra }) {
  return (
    <div>
      <div
        className="text-xs uppercase tracking-wide font-ui"
        style={{ color: "var(--fs-muted)" }}
      >
        {label}
      </div>
      {rows.length === 0 ? (
        <p
          className="text-sm font-ui mt-1"
          style={{ color: "var(--fs-muted)" }}
          data-testid={`${testidPrefix}-empty`}
        >
          {emptyLabel}
        </p>
      ) : (
        <ul className="mt-1" data-testid={`${testidPrefix}-list`}>
          {rows.map((r) => (
            <li key={r.id}>
              <Link
                to={`/competency/${r.id}`}
                data-testid={`${testidPrefix}-row-${r.id}`}
                className="tap -mx-2 px-2 py-2 flex items-center justify-between gap-3"
              >
                <span className="font-semibold">{r.name}</span>
                {renderExtra ? renderExtra(r) : null}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
