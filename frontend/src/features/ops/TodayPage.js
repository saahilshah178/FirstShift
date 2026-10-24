import React, { useEffect, useState } from "react";
import { api } from "@/api";

const FLAGS = { en: "🇺🇸", es: "🇪🇸", tl: "🇵🇭" };

export default function TodayPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/ops/caregivers")
      .then((r) => setState({ status: "ok", rows: r.data.caregivers }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="today-page" className="space-y-4">
      <header className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Today</h1>
          <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
            Shift-ready caregivers across your agencies.
          </p>
        </div>
        {state.status === "ok" ? (
          <span className="fs-chip" data-testid="today-count">
            {state.rows.length} on-call
          </span>
        ) : null}
      </header>

      {state.status === "loading" ? (
        <SkeletonList />
      ) : state.status === "error" ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }}>
          {state.error}
        </p>
      ) : (
        <ul className="fs-card fs-divider" data-testid="today-list">
          {state.rows.map((c) => (
            <li
              key={c.id}
              className="px-4 py-3 flex items-center justify-between"
              data-testid={`today-row-${c.id}`}
            >
              <div className="flex items-center gap-3">
                <span className="text-xl" aria-hidden>
                  {FLAGS[c.language] ?? "🏳️"}
                </span>
                <div>
                  <div className="font-semibold">{c.name}</div>
                  <div
                    className="text-xs font-ui"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {c.experience_note}
                  </div>
                </div>
              </div>
              <code
                className="font-ui text-xs tracking-wider px-2 py-1 rounded"
                style={{ background: "var(--fs-accent)" }}
              >
                {c.access_code}
              </code>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function SkeletonList() {
  return (
    <ul className="fs-card fs-divider" data-testid="today-skeleton">
      {Array.from({ length: 3 }).map((_, i) => (
        <li key={i} className="px-4 py-3">
          <div
            className="h-4 w-32 rounded"
            style={{ background: "var(--fs-accent)" }}
          />
          <div
            className="mt-2 h-3 w-56 rounded"
            style={{ background: "var(--fs-accent)" }}
          />
        </li>
      ))}
    </ul>
  );
}
