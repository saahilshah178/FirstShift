import React, { useEffect, useState } from "react";
import { api } from "@/api";

export default function QuestionsPage() {
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get("/questions/list")
      .then((r) => setState({ status: "ok", rows: r.data.questions }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="questions-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Questions</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Caregiver questions waiting on an answer.
        </p>
      </header>
      {state.status === "ok" ? (
        state.rows.length === 0 ? (
          <div
            className="fs-card px-5 py-10 text-center"
            data-testid="questions-empty"
          >
            <p className="text-base" style={{ color: "var(--fs-fg)" }}>
              No questions yet.
            </p>
            <p
              className="mt-1 text-sm font-ui"
              style={{ color: "var(--fs-muted)" }}
            >
              When a caregiver asks, their question will land here.
            </p>
          </div>
        ) : (
          <ul className="fs-card fs-divider" data-testid="questions-list">
            {state.rows.map((q, i) => (
              <li key={i} className="px-4 py-3">
                <pre className="text-xs font-ui whitespace-pre-wrap">
                  {JSON.stringify(q, null, 2)}
                </pre>
              </li>
            ))}
          </ul>
        )
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
