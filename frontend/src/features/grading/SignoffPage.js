import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api";

const TABS = [
  { key: "ready_to_sign", label: "Ready to sign" },
  { key: "needs_practice", label: "Needs practice" },
];

export default function SignoffPage() {
  const [state, setState] = useState({ status: "loading" });
  const [tab, setTab] = useState("ready_to_sign");

  useEffect(() => {
    // Stage 4-G: shared GET dedupe in api.js collapses the StrictMode
    // double-mount into one network request.
    api
      .get("/grading/queue")
      .then((r) => setState({ status: "ok", data: r.data }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  return (
    <section data-testid="signoff-page" className="space-y-4">
      <header>
        <h1 className="text-2xl font-semibold">Sign-off</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Attempts waiting on your decision.
        </p>
      </header>
      <nav
        className="flex rounded-full border p-1"
        style={{ borderColor: "var(--fs-border)" }}
        data-testid="signoff-tabs"
      >
        {TABS.map((t) => (
          <button
            key={t.key}
            type="button"
            onClick={() => setTab(t.key)}
            data-testid={`signoff-tab-${t.key}`}
            className={[
              "flex-1 tap text-sm font-ui rounded-full",
              tab === t.key
                ? "bg-[color:var(--fs-primary)] text-[color:var(--fs-primary-fg)]"
                : "text-[color:var(--fs-muted)]",
            ].join(" ")}
          >
            {t.label}
            {state.status === "ok" ? (
              <span className="ml-1 opacity-70">
                ({(state.data[t.key] || []).length})
              </span>
            ) : null}
          </button>
        ))}
      </nav>

      {state.status === "ok" ? (
        <List rows={state.data[tab] || []} testid={`signoff-list-${tab}`} />
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

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

function List({ rows, testid }) {
  if (rows.length === 0) {
    return (
      <div
        className="fs-card px-5 py-8 text-center"
        data-testid={`${testid}-empty`}
      >
        <p className="font-ui text-sm" style={{ color: "var(--fs-muted)" }}>
          Nothing here yet.
        </p>
      </div>
    );
  }
  return (
    <ul className="grid grid-cols-1 gap-3" data-testid={testid}>
      {rows.map((a) => (
        <li key={a.id}>
          <Link
            to={`/signoff/${a.id}`}
            className="fs-card p-4 flex items-start justify-between gap-3 tap"
            data-testid={`signoff-row-${a.id}`}
          >
            <div className="min-w-0 flex-1">
              <div className="font-semibold break-words">
                {a.caregiver.name}
              </div>
              <div
                className="font-ui text-xs break-words"
                style={{ color: "var(--fs-muted)" }}
              >
                {a.skill.title}
                <span className="whitespace-nowrap"> · {fmtDate(a.created_at)}</span>
              </div>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              {typeof a.score === "number" ? (
                <span className="fs-chip whitespace-nowrap">
                  {Math.round(a.score * 100)}%
                </span>
              ) : null}
              {a.graded_once ? (
                <span
                  className="fs-chip fs-chip-warn whitespace-nowrap"
                  data-testid={`signoff-row-${a.id}-graded-once`}
                >
                  graded once
                </span>
              ) : null}
            </div>
          </Link>
        </li>
      ))}
    </ul>
  );
}
