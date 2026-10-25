import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "@/api";
import { useRole, canRecordSkill } from "@/hooks/useRole";

function stageLabel(status) {
  switch (status) {
    case "uploading":
      return "Uploading";
    case "converting":
      return "Converting";
    case "analyzing":
      return "Analyzing";
    case "extracting_frames":
      return "Extracting frames";
    case "ready":
      return "Ready to review";
    case "publishing":
      return "Publishing";
    case "published":
      return "Published";
    case "failed":
      return "Failed";
    default:
      return status || "Unknown";
  }
}

function stageTone(status) {
  if (status === "ready") return "var(--fs-pass)";
  if (status === "failed") return "var(--fs-fail)";
  if (status === "published") return "var(--fs-muted)";
  return "var(--fs-warn)";
}

export default function SkillsPage() {
  const nav = useNavigate();
  const role = useRole();
  const canRecord = canRecordSkill(role);
  const [skills, setSkills] = useState(null);
  const [jobs, setJobs] = useState([]);
  const [err, setErr] = useState(null);

  const load = useMemo(
    () => async () => {
      try {
        const [s, j] = await Promise.all([
          api.get("/lessons/skills"),
          canRecord ? api.get("/lessons/jobs") : Promise.resolve({ data: { jobs: [] } }),
        ]);
        setSkills(s.data.skills || []);
        setJobs(j.data.jobs || []);
      } catch (e) {
        setErr(e?.message || "failed");
      }
    },
    [canRecord],
  );

  useEffect(() => {
    load();
  }, [load]);

  // Poll jobs when some are active.
  useEffect(() => {
    const active = jobs.some((j) =>
      ["converting", "analyzing", "extracting_frames", "publishing", "uploading"].includes(j.status),
    );
    if (!active) return undefined;
    const t = setInterval(() => load(), 2000);
    return () => clearInterval(t);
  }, [jobs, load]);

  return (
    <section data-testid="skills-page" className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Skills</h1>
          <p
            className="text-sm font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            Every skill a caregiver can be checked on.
          </p>
        </div>
        {canRecord ? (
          <button
            type="button"
            onClick={() => nav("/skills/record")}
            data-testid="record-skill-btn"
            className="tap px-4 rounded-full font-ui text-sm"
            style={{
              background: "var(--fs-primary)",
              color: "var(--fs-primary-fg)",
            }}
          >
            Record a skill
          </button>
        ) : null}
      </header>

      {!canRecord ? (
        <p
          className="text-xs font-ui fs-card px-4 py-2"
          style={{ color: "var(--fs-muted)" }}
          data-testid="skills-role-note"
        >
          Scheduler view — read only. Switch to Care Manager or Trainer to record or edit skills.
        </p>
      ) : null}

      {err ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }} data-testid="skills-error">
          {err}
        </p>
      ) : null}

      {canRecord && jobs.length > 0 ? (
        <section data-testid="jobs-section">
          <h2
            className="text-xs uppercase tracking-wide font-ui mb-2"
            style={{ color: "var(--fs-muted)" }}
          >
            Drafts & in-progress ({jobs.length})
          </h2>
          <ul className="fs-card fs-divider" data-testid="jobs-list">
            {jobs.map((j) => (
              <li
                key={j.id}
                data-testid={`job-row-${j.id}`}
                className="px-4 py-3 flex items-center justify-between gap-3"
              >
                <div className="min-w-0">
                  <Link
                    to={`/skills/drafts/${j.id}`}
                    className="font-semibold truncate block"
                    data-testid={`job-link-${j.id}`}
                  >
                    {j.draft?.title || "(no title yet)"}
                  </Link>
                  <div
                    className="text-xs font-ui mt-0.5"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {new Date(j.updated_at).toLocaleString()}
                    {j.source_credit ? ` · ${j.source_credit}` : ""}
                  </div>
                </div>
                <span
                  className="fs-chip"
                  style={{
                    color: stageTone(j.status),
                    borderColor: stageTone(j.status),
                  }}
                  data-testid={`job-status-${j.id}`}
                >
                  {stageLabel(j.status)}
                </span>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section data-testid="published-section">
        <h2
          className="text-xs uppercase tracking-wide font-ui mb-2"
          style={{ color: "var(--fs-muted)" }}
        >
          Published ({skills ? skills.length : "…"})
        </h2>
        {skills === null ? (
          <p className="text-sm" style={{ color: "var(--fs-muted)" }}>
            Loading…
          </p>
        ) : skills.length === 0 ? (
          <p
            className="text-sm fs-card px-4 py-3"
            style={{ color: "var(--fs-muted)" }}
          >
            No skills yet. Record your first one above.
          </p>
        ) : (
          <ul className="fs-card fs-divider" data-testid="skills-list">
            {skills.map((s) => (
              <li key={s.id} data-testid={`skills-row-${s.id}`}>
                <Link
                  to={`/skills/${s.id}`}
                  data-testid={`skill-link-${s.id}`}
                  className="tap flex items-center justify-between gap-3 px-4 py-3"
                >
                  <span className="font-semibold truncate flex-1 min-w-0">
                    {s.title}
                  </span>
                  <span
                    className="text-xs font-ui whitespace-nowrap"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {s.step_count} steps · {s.check_count} checks
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </section>
  );
}
