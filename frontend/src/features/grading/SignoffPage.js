import React, { useEffect, useState } from "react";
import { api } from "@/api";

function scoreChip(score) {
  if (score == null) return "fs-chip";
  if (score >= 85) return "fs-chip fs-chip-pass";
  if (score >= 65) return "fs-chip fs-chip-warn";
  return "fs-chip fs-chip-fail";
}

export default function SignoffPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/grading/attempts")
      .then((r) => setState({ status: "ok", rows: r.data.attempts }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="signoff-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Sign-off</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Recent attempts waiting on your decision.
        </p>
      </header>
      {state.status === "ok" ? (
        <ul className="fs-card fs-divider" data-testid="signoff-list">
          {state.rows.map((a) => (
            <li
              key={a.id}
              className="px-4 py-3"
              data-testid={`signoff-row-${a.id}`}
            >
              <div className="flex items-center justify-between">
                <div>
                  <div className="font-semibold">{a.caregiver.name}</div>
                  <div
                    className="text-xs font-ui"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {a.skill.title}
                  </div>
                </div>
                <span
                  className={scoreChip(a.overall)}
                  data-testid={`signoff-score-${a.id}`}
                >
                  {a.overall ?? "—"}
                </span>
              </div>
              <div
                className="mt-2 text-xs font-ui"
                style={{ color: "var(--fs-muted)" }}
              >
                {a.check_results.length} checks ·{" "}
                {a.check_results.filter((c) => c.result === "pass").length}{" "}
                passed
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
