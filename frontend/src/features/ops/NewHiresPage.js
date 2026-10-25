import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
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
    const ac = new AbortController();
    api
      .get("/ops/caregivers?sort=hired_at_desc", { signal: ac.signal })
      .then((r) => setState({ status: "ok", rows: r.data.caregivers }))
      .catch((e) => {
        if (
          e?.name === "CanceledError" ||
          e?.name === "AbortError" ||
          e?.code === "ERR_CANCELED"
        )
          return;
        setState({ status: "error", error: e?.message || "failed" });
      });
    return () => ac.abort();
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
            <li key={c.id} data-testid={`newhires-row-${c.id}`}>
              {/* Stage 4-C: whole row is a Link to the caregiver's
                  competency file. Full-width tap target; break-words
                  on name + experience note so long strings don't
                  overflow at ~480px. */}
              <Link
                to={`/competency/${c.id}`}
                data-testid={`newhires-link-${c.id}`}
                className="tap flex items-start justify-between gap-3 px-4 py-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold flex items-center gap-2 flex-wrap">
                    <span aria-hidden>{FLAGS[c.language] ?? "🏳️"}</span>
                    <span className="break-words">{c.name}</span>
                    {i === 0 ? (
                      <span className="fs-chip fs-chip-pass whitespace-nowrap">
                        newest
                      </span>
                    ) : null}
                  </div>
                  {c.experience_note ? (
                    <div
                      className="text-xs font-ui mt-1 break-words"
                      style={{ color: "var(--fs-muted)" }}
                    >
                      {c.experience_note}
                    </div>
                  ) : null}
                </div>
                <div className="text-right shrink-0">
                  <div className="font-semibold font-ui tabular-nums">
                    {daysSince(c.hired_at)}d
                  </div>
                  <div
                    className="text-[11px] font-ui whitespace-nowrap"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    since hire
                  </div>
                </div>
              </Link>
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
