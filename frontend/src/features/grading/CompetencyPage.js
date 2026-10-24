import React, { useEffect, useState } from "react";
import { api } from "@/api";

export default function CompetencyPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/grading/competency")
      .then((r) => setState({ status: "ok", data: r.data }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="competency-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Competency files</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Caregivers grouped by how many skills they've cleared.
        </p>
      </header>
      {state.status === "ok" ? (
        <Grouped data={state.data} />
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

function Grouped({ data }) {
  const groups = new Map();
  for (const c of data.caregivers) {
    const k = c.cleared_count;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(c);
  }
  const keys = [...groups.keys()].sort((a, b) => b - a);
  return (
    <div className="space-y-5" data-testid="competency-groups">
      {keys.map((k) => (
        <div key={k}>
          <div
            className="text-xs uppercase tracking-wide font-ui mb-2"
            style={{ color: "var(--fs-muted)" }}
          >
            {k} / {data.total_skills} cleared · {groups.get(k).length}{" "}
            caregiver{groups.get(k).length === 1 ? "" : "s"}
          </div>
          <ul
            className="fs-card fs-divider"
            data-testid={`competency-group-${k}`}
          >
            {groups.get(k).map((c) => (
              <li
                key={c.id}
                className="px-4 py-3 flex items-start justify-between gap-3"
              >
                <div className="font-semibold">{c.name}</div>
                <div className="flex flex-wrap justify-end gap-1 max-w-[60%]">
                  {c.cleared.length === 0 ? (
                    <span
                      className="text-xs font-ui"
                      style={{ color: "var(--fs-muted)" }}
                    >
                      None yet
                    </span>
                  ) : (
                    c.cleared.map((s) => (
                      <span key={s.id} className="fs-chip fs-chip-pass">
                        {s.title}
                      </span>
                    ))
                  )}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
