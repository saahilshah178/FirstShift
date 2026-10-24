import React, { useEffect, useState } from "react";
import { api } from "@/api";

const FLAGS = { en: "🇺🇸", es: "🇪🇸", tl: "🇵🇭" };

function daysSince(iso) {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  const now = Date.now();
  return Math.max(0, Math.round((now - then) / (1000 * 60 * 60 * 24)));
}

export default function NewHiresPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/ops/caregivers?sort=hired_at_desc")
      .then((r) => setState({ status: "ok", rows: r.data.caregivers }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="newhires-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">New hires</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Caregivers sorted by hire date, newest first.
        </p>
      </header>
      {state.status === "ok" ? (
        <ul className="fs-card fs-divider" data-testid="newhires-list">
          {state.rows.map((c, i) => (
            <li
              key={c.id}
              className="px-4 py-3"
              data-testid={`newhires-row-${c.id}`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold flex items-center gap-2">
                    <span aria-hidden>{FLAGS[c.language] ?? "🏳️"}</span>
                    {c.name}
                    {i === 0 ? (
                      <span className="fs-chip fs-chip-pass">newest</span>
                    ) : null}
                  </div>
                  <div
                    className="text-xs font-ui mt-1"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {c.experience_note}
                  </div>
                </div>
                <div className="text-right">
                  <div className="font-semibold font-ui tabular-nums">
                    {daysSince(c.hired_at)}d
                  </div>
                  <div
                    className="text-[11px] font-ui"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    since hire
                  </div>
                </div>
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
