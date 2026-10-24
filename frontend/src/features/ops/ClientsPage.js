import React, { useEffect, useState } from "react";
import { api } from "@/api";

export default function ClientsPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/ops/clients")
      .then((r) => setState({ status: "ok", rows: r.data.clients }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="clients-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Clients</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Each client with the skills their caregivers must have cleared.
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
              className="fs-card p-4"
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
