import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, absoluteUrl } from "@/api";

function fmtDate(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    return d.toLocaleDateString(undefined, {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return iso;
  }
}

const STATUS_CHIP = {
  cleared: "fs-chip fs-chip-pass",
  not_cleared: "fs-chip fs-chip-warn",
  not_attempted: "fs-chip",
};

const STATUS_LABEL = {
  cleared: "Cleared",
  not_cleared: "Not cleared",
  not_attempted: "Not attempted",
};

export default function CompetencyDetailPage() {
  const { caregiverId } = useParams();
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [expanded, setExpanded] = useState({});

  useEffect(() => {
    api
      .get(`/grading/competency/${caregiverId}`)
      .then((r) => setData(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || e.message));
  }, [caregiverId]);

  if (err) {
    return (
      <section className="space-y-2" data-testid="competency-detail-error">
        <Link to="/competency" className="font-ui text-sm underline">
          ← Competency files
        </Link>
        <p style={{ color: "var(--fs-fail)" }}>{err}</p>
      </section>
    );
  }
  if (!data) {
    return (
      <p className="font-ui text-sm" style={{ color: "var(--fs-muted)" }}>
        Loading…
      </p>
    );
  }

  return (
    <section
      className="space-y-5"
      data-testid="competency-detail-page"
      data-caregiver-id={caregiverId}
    >
      <Link to="/competency" className="font-ui text-sm underline">
        ← Competency files
      </Link>
      <header>
        <h1 className="text-2xl font-semibold">{data.caregiver.name}</h1>
        <p
          className="text-sm font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          Every skill, with history.
        </p>
      </header>

      <ul
        className="grid grid-cols-1 gap-3"
        data-testid="competency-detail-list"
      >
        {data.skills.map((row) => {
          const open = !!expanded[row.skill.id];
          return (
            <li
              key={row.skill.id}
              className="fs-card p-4"
              data-testid={`competency-row-${row.skill.id}`}
            >
              <div className="flex items-center justify-between gap-3">
                <div>
                  <div className="font-semibold">{row.skill.title}</div>
                  <div
                    className="font-ui text-xs"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {row.latest
                      ? `latest ${fmtDate(row.latest.date)}`
                      : "No attempts yet"}
                  </div>
                </div>
                <span className={STATUS_CHIP[row.status]}>
                  {STATUS_LABEL[row.status]}
                </span>
              </div>

              {row.latest ? (
                <div className="mt-4 space-y-3">
                  <div
                    className="font-ui text-xs"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {row.latest.decision === "approve" ? (
                      <>
                        Signed by{" "}
                        <span className="font-semibold">
                          {row.latest.signer}
                        </span>
                        {row.latest.signer_role
                          ? ` (${row.latest.signer_role})`
                          : null}
                        {row.latest.override ? (
                          <span
                            className="ml-2 fs-chip fs-chip-warn"
                            data-testid={`competency-override-${row.skill.id}`}
                          >
                            override
                          </span>
                        ) : null}
                      </>
                    ) : row.latest.decision === "send_back" ? (
                      <>Sent back by {row.latest.signer}</>
                    ) : (
                      <>Awaiting decision</>
                    )}
                  </div>
                  {/* Fix #9 — surface the override / send-back note itself,
                      with breathing room above the video thumbnail. */}
                  {row.latest.note && row.latest.decision ? (
                    <blockquote
                      className="font-ui text-sm px-3 py-2 rounded-lg border-l-2"
                      data-testid={`competency-note-${row.skill.id}`}
                      style={{
                        background: "var(--fs-accent)",
                        borderLeftColor:
                          row.latest.override || row.latest.decision === "send_back"
                            ? "var(--fs-warn)"
                            : "var(--fs-border)",
                        color: "var(--fs-fg)",
                        whiteSpace: "pre-wrap",
                      }}
                    >
                      “{row.latest.note}”
                    </blockquote>
                  ) : null}
                  {row.latest.clip_id ? (
                    <video
                      src={absoluteUrl(`/api/media/${row.latest.clip_id}`)}
                      controls
                      playsInline
                      className="w-full rounded-lg border"
                      style={{ borderColor: "var(--fs-border)" }}
                      data-testid={`competency-video-${row.skill.id}`}
                    />
                  ) : null}
                </div>
              ) : null}

              {row.history.length > 1 ? (
                <button
                  type="button"
                  onClick={() =>
                    setExpanded((s) => ({
                      ...s,
                      [row.skill.id]: !s[row.skill.id],
                    }))
                  }
                  className="mt-3 font-ui text-xs underline"
                  data-testid={`competency-history-toggle-${row.skill.id}`}
                >
                  {open
                    ? "Hide history"
                    : `Show ${row.history.length - 1} earlier`}
                </button>
              ) : null}
              {open && row.history.length > 1 ? (
                <ul
                  className="mt-3 fs-divider border-t"
                  style={{ borderColor: "var(--fs-border)" }}
                  data-testid={`competency-history-${row.skill.id}`}
                >
                  {row.history.slice(1).map((h) => (
                    <li
                      key={h.attempt_id}
                      className="py-2 flex items-center justify-between"
                    >
                      <span
                        className="font-ui text-xs"
                        style={{ color: "var(--fs-muted)" }}
                      >
                        {fmtDate(h.date)} ·{" "}
                        {h.decision ? h.decision : "no decision"}
                      </span>
                      <span className="fs-chip">{h.overall ?? "—"}</span>
                    </li>
                  ))}
                </ul>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
