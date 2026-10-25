import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "@/api";

const FLAGS = { en: "🇺🇸", es: "🇪🇸", tl: "🇵🇭" };

export default function TodayPage() {
  const [metrics, setMetrics] = useState({ status: "loading" });
  const [drilldown, setDrilldown] = useState({ open: false, rows: null });

  const fetchMetrics = React.useCallback(() => {
    api
      .get("/ops/today/metrics")
      .then((r) => setMetrics({ status: "ok", data: r.data }))
      .catch((e) =>
        setMetrics({ status: "error", error: e?.message || "failed" }),
      );
  }, []);

  useEffect(() => {
    // Stage 4-G: the shared GET dedupe in api.js collapses the
    // StrictMode double-mount into a single network request. No local
    // AbortController required.
    fetchMetrics();
  }, [fetchMetrics]);

  // Stage 4-G: Today refreshes on tab focus / visibility change, not
  // on a poll. The headline + card counts don't move second-to-second
  // but should pick up a fresh signoff when the Care Manager alt-tabs
  // back to the dashboard.
  useEffect(() => {
    const onFocus = () => fetchMetrics();
    const onVis = () => {
      if (document.visibilityState === "visible") fetchMetrics();
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onVis);
    return () => {
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [fetchMetrics]);

  const openDrilldown = async () => {
    if (drilldown.rows) {
      setDrilldown((d) => ({ ...d, open: true }));
      return;
    }
    try {
      const r = await api.get("/ops/today/cleared-days");
      setDrilldown({ open: true, rows: r.data.rows });
    } catch (e) {
      setDrilldown({ open: true, rows: [] });
    }
  };

  return (
    <section data-testid="today-page" className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Today</h1>
        <p
          className="text-sm font-ui"
          style={{ color: "var(--fs-muted)" }}
          data-testid="today-sub"
        >
          Agency ops snapshot.
        </p>
      </header>

      {metrics.status === "loading" ? (
        <SkeletonCards />
      ) : metrics.status === "error" ? (
        <p
          className="text-sm"
          style={{ color: "var(--fs-fail)" }}
          data-testid="today-error"
        >
          {metrics.error}
        </p>
      ) : (
        <>
          <div
            className="grid grid-cols-1 gap-3"
            data-testid="today-cards"
          >
            <Card
              testid="today-card-new-hires"
              to="/caregivers?filter=new-30d-in-progress"
              label="New hires in progress"
              value={metrics.data.cards.new_hires_in_progress}
              hint="hired in the last 30 days with items still open"
            />
            <Card
              testid="today-card-signoffs"
              to="/signoff"
              label="Sign-offs waiting"
              value={metrics.data.cards.signoffs_waiting}
              hint="attempts ready to review"
            />
            <Card
              testid="today-card-questions"
              to="/questions"
              label="Open questions"
              value={metrics.data.cards.open_questions}
              hint="caregiver questions awaiting a reply"
            />
          </div>

          <div
            className="fs-card p-4"
            data-testid="today-headline-metric"
          >
            <div className="flex items-end justify-between">
              <div>
                <div
                  className="text-xs uppercase tracking-wide font-ui"
                  style={{ color: "var(--fs-muted)" }}
                >
                  Avg time to cleared
                </div>
                {metrics.data.avg_days_to_cleared == null ? (
                  <div
                    className="text-base font-ui mt-1"
                    data-testid="today-avg-days"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    Not enough data yet
                  </div>
                ) : (
                  <>
                    <div
                      className="text-3xl font-semibold mt-1"
                      data-testid="today-avg-days"
                    >
                      {metrics.data.avg_days_to_cleared} days
                    </div>
                    <div
                      className="text-xs font-ui mt-1"
                      style={{ color: "var(--fs-muted)" }}
                    >
                      across {metrics.data.fully_cleared_count} fully-cleared
                      caregiver
                      {metrics.data.fully_cleared_count === 1 ? "" : "s"}
                    </div>
                  </>
                )}
              </div>
              {metrics.data.avg_days_to_cleared != null ? (
                <button
                  type="button"
                  onClick={openDrilldown}
                  data-testid="today-avg-days-drilldown-btn"
                  className="tap px-3 text-xs font-ui rounded-full border"
                  style={{ borderColor: "var(--fs-border)" }}
                >
                  See breakdown
                </button>
              ) : null}
            </div>
          </div>
        </>
      )}

      {drilldown.open ? (
        <DrilldownDialog
          rows={drilldown.rows || []}
          onClose={() => setDrilldown((d) => ({ ...d, open: false }))}
        />
      ) : null}
    </section>
  );
}

function Card({ to, label, value, hint, testid }) {
  const content = (
    <div className="flex items-start gap-3">
      <div className="min-w-0 flex-1">
        <h2 className="text-xs font-ui font-semibold uppercase tracking-wide">
          {label}
        </h2>
        <p
          className="text-xs font-ui mt-1 break-words"
          style={{ color: "var(--fs-muted)" }}
        >
          {hint}
        </p>
      </div>
      <span
        className="text-3xl font-semibold tabular-nums shrink-0 leading-none mt-0.5"
        data-testid={`${testid}-value`}
      >
        {value}
      </span>
    </div>
  );
  return (
    <Link
      to={to}
      className="fs-card p-4 tap block"
      data-testid={testid}
    >
      {content}
    </Link>
  );
}

function DrilldownDialog({ rows, onClose }) {
  return (
    <div
      role="dialog"
      aria-label="Avg days to cleared breakdown"
      className="fixed inset-0 z-30 flex items-end sm:items-center justify-center"
      style={{ background: "rgba(0,0,0,0.3)" }}
      data-testid="today-avg-days-drilldown"
      onClick={onClose}
    >
      <div
        className="fs-card w-full sm:max-w-md p-4 space-y-3"
        style={{ background: "var(--fs-surface)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Avg time to cleared</h3>
          <button
            type="button"
            onClick={onClose}
            data-testid="today-avg-days-drilldown-close"
            className="tap text-sm font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            Close
          </button>
        </header>
        {rows.length === 0 ? (
          <p
            className="text-sm font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            No fully-cleared caregivers yet.
          </p>
        ) : (
          <ul className="fs-divider">
            {rows.map((r) => (
              <li
                key={r.caregiver_id}
                className="py-2 flex items-center justify-between"
                data-testid={`today-cleared-row-${r.caregiver_id}`}
              >
                <Link
                  to={`/competency/${r.caregiver_id}`}
                  className="font-semibold"
                >
                  {r.name}
                </Link>
                <span
                  className="font-ui text-xs"
                  style={{ color: "var(--fs-muted)" }}
                >
                  {r.days} days
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function SkeletonCards() {
  return (
    <div className="grid grid-cols-1 gap-3" data-testid="today-skeleton">
      {Array.from({ length: 3 }).map((_, i) => (
        <div
          key={i}
          className="fs-card p-4 h-20"
          style={{ background: "var(--fs-accent)" }}
        />
      ))}
    </div>
  );
}

// Preserve flag constants for existing callers; nothing else references
// them inside this file after the Stage 3 rewrite.
export { FLAGS };
