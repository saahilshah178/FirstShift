import React, { useEffect, useState } from "react";
import { api } from "@/api";

export default function SkillsPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/lessons/skills")
      .then((r) => setState({ status: "ok", rows: r.data.skills }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="skills-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Skills</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Every skill a caregiver can be checked on.
        </p>
      </header>
      {state.status === "ok" ? (
        <ul className="fs-card fs-divider" data-testid="skills-list">
          {state.rows.map((s) => (
            <li
              key={s.id}
              className="px-4 py-3 flex items-center justify-between"
              data-testid={`skills-row-${s.id}`}
            >
              <div className="font-semibold">{s.title}</div>
              <div
                className="text-xs font-ui"
                style={{ color: "var(--fs-muted)" }}
              >
                {s.step_count} steps · {s.check_count} checks
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
