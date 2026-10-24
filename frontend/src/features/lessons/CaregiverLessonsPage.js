import React, { useEffect, useState } from "react";
import { api } from "@/api";
import { useCaregiver } from "@/shell/CaregiverLayout";

export default function CaregiverLessonsPage() {
  const { caregiver } = useCaregiver();
  const [state, setState] = useState({ status: "loading" });

  useEffect(() => {
    api
      .get(`/lessons/caregiver/${caregiver.id}`)
      .then((r) => setState({ status: "ok", data: r.data }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, [caregiver.id]);

  if (state.status !== "ok") {
    return (
      <div className="px-5 py-6" data-testid="caregiver-lessons-page">
        <h2 className="text-xl font-semibold">Lessons</h2>
        {state.status === "error" ? (
          <p className="mt-2 text-sm" style={{ color: "var(--fs-fail)" }}>
            {state.error}
          </p>
        ) : (
          <p className="mt-2 text-sm" style={{ color: "var(--fs-muted)" }}>
            Loading…
          </p>
        )}
      </div>
    );
  }

  const { cleared, remaining } = state.data;
  return (
    <div className="px-5 py-6 space-y-6" data-testid="caregiver-lessons-page">
      <h2 className="text-xl font-semibold">Lessons</h2>

      <section>
        <h3
          className="text-xs uppercase tracking-wide font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          Cleared ({cleared.length})
        </h3>
        {cleared.length === 0 ? (
          <p
            className="mt-2 text-sm font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            Nothing cleared yet.
          </p>
        ) : (
          <ul
            className="mt-2 fs-card fs-divider"
            data-testid="caregiver-lessons-cleared"
          >
            {cleared.map((s) => (
              <li
                key={s.id}
                className="px-4 py-3 flex items-center justify-between"
              >
                <span className="font-semibold">{s.title}</span>
                <span className="fs-chip fs-chip-pass">cleared</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <h3
          className="text-xs uppercase tracking-wide font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          Remaining ({remaining.length})
        </h3>
        {remaining.length === 0 ? (
          <p
            className="mt-2 text-sm font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            All caught up.
          </p>
        ) : (
          <ul
            className="mt-2 fs-card fs-divider"
            data-testid="caregiver-lessons-remaining"
          >
            {remaining.map((s) => (
              <li
                key={s.id}
                className="px-4 py-3 flex items-center justify-between"
              >
                <div>
                  <div className="font-semibold">{s.title}</div>
                  <div
                    className="text-xs font-ui"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {s.step_count} steps
                  </div>
                </div>
                <span className="fs-chip">to do</span>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
