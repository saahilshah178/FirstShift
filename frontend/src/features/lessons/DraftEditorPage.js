import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, absoluteUrl } from "@/api";
import { useRole, canEditSkill } from "@/hooks/useRole";

const STAGE_ORDER = [
  { k: "converting", label: "Converting" },
  { k: "analyzing", label: "Analyzing" },
  { k: "extracting_frames", label: "Extracting frames" },
  { k: "ready", label: "Ready to review" },
];

function stageIndex(status) {
  const i = STAGE_ORDER.findIndex((s) => s.k === status);
  if (i >= 0) return i;
  if (status === "publishing" || status === "published") return STAGE_ORDER.length;
  return 0;
}

function fmtTime(s) {
  if (s === null || s === undefined || Number.isNaN(Number(s))) return "0:00.0";
  const sec = Math.max(0, Number(s));
  const m = Math.floor(sec / 60);
  const r = sec - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
}
function parseTime(str) {
  if (typeof str === "number") return str;
  if (typeof str !== "string") return 0;
  const t = str.trim();
  if (t.includes(":")) {
    const [m, r] = t.split(":");
    const n = parseFloat(m) * 60 + parseFloat(r);
    return Number.isFinite(n) ? n : 0;
  }
  const n = parseFloat(t);
  return Number.isFinite(n) ? n : 0;
}

export default function DraftEditorPage() {
  const { jobId } = useParams();
  const nav = useNavigate();
  const role = useRole();
  const allowed = canEditSkill(role);
  const [job, setJob] = useState(null);
  const [err, setErr] = useState(null);
  const [savingStep, setSavingStep] = useState(false);
  const [publishError, setPublishError] = useState(null);
  const pollRef = useRef(null);

  const load = useMemo(
    () => async () => {
      try {
        const r = await api.get(`/lessons/jobs/${jobId}`);
        setJob(r.data);
        setErr(null);
      } catch (e) {
        const detail = e?.response?.data?.detail;
        setErr(typeof detail === "string" ? detail : e?.message || "failed");
      }
    },
    [jobId],
  );

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    if (!job) return undefined;
    const terminal = ["ready", "failed", "published"].includes(job.status);
    if (terminal) return undefined;
    pollRef.current = setInterval(() => load(), 2000);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [job?.status, load, job]);

  if (!allowed) {
    return (
      <section className="space-y-3" data-testid="draft-page-gate">
        <h1 className="text-2xl font-semibold">Draft</h1>
        <p
          className="text-sm font-ui fs-card px-4 py-3"
          style={{ color: "var(--fs-muted)" }}
        >
          Switch to Care Manager or Trainer to edit skills.
        </p>
      </section>
    );
  }

  if (err && !job) {
    return (
      <section className="space-y-3" data-testid="draft-error">
        <h1 className="text-2xl font-semibold">Draft</h1>
        <p className="text-sm" style={{ color: "var(--fs-fail)" }}>{err}</p>
        <Link to="/skills" className="text-sm font-ui">Back to Skills</Link>
      </section>
    );
  }
  if (!job) {
    return <p data-testid="draft-loading" style={{ color: "var(--fs-muted)" }}>Loading…</p>;
  }

  if (job.status === "published" && job.skill_id) {
    // After publish — redirect helper.
    return (
      <section className="space-y-3" data-testid="draft-published">
        <p>Published.</p>
        <Link to={`/skills/${job.skill_id}`} className="text-sm font-ui" data-testid="draft-view-skill">
          View skill
        </Link>
      </section>
    );
  }

  const idx = stageIndex(job.status);

  return (
    <section className="space-y-5" data-testid="draft-page">
      <header className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold truncate">
            {job.draft?.title || "Draft"}
          </h1>
          <p className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
            {job.source_credit || "No source credit"}
          </p>
        </div>
        <Link to="/skills" className="text-sm font-ui" data-testid="draft-back">
          Back
        </Link>
      </header>

      {/* Stage list */}
      {job.status !== "ready" && job.status !== "failed" && job.status !== "published" ? (
        <ol className="fs-card fs-divider" data-testid="draft-stages">
          {STAGE_ORDER.map((s, i) => {
            const done = i < idx;
            const active = i === idx;
            return (
              <li
                key={s.k}
                className="px-4 py-3 flex items-center justify-between"
                data-testid={`stage-${s.k}`}
              >
                <span
                  className={active ? "font-semibold" : ""}
                  style={{ color: done ? "var(--fs-pass)" : active ? "var(--fs-fg)" : "var(--fs-muted)" }}
                >
                  {s.label}
                </span>
                {done ? (
                  <span className="fs-chip" data-testid={`stage-chip-${s.k}`}>done</span>
                ) : active ? (
                  <span className="fs-chip" style={{ color: "var(--fs-warn)" }} data-testid={`stage-chip-${s.k}`}>
                    running…
                  </span>
                ) : null}
              </li>
            );
          })}
        </ol>
      ) : null}

      {job.status === "failed" ? (
        <div className="fs-card p-4 space-y-3" data-testid="draft-failed">
          <p style={{ color: "var(--fs-fail)" }} data-testid="draft-failed-error">
            {job.error || "Failed"}
          </p>
          <button
            type="button"
            data-testid="draft-retry-btn"
            onClick={async () => {
              try {
                await api.post(`/lessons/jobs/${jobId}/retry`);
                await load();
              } catch (e) {
                setErr(e?.message || "retry failed");
              }
            }}
            className="tap px-4 rounded-full font-ui text-sm"
            style={{ background: "var(--fs-primary)", color: "var(--fs-primary-fg)" }}
          >
            Retry
          </button>
        </div>
      ) : null}

      {job.status === "ready" ? (
        <Editor
          job={job}
          onChange={setJob}
          savingStep={savingStep}
          setSavingStep={setSavingStep}
          publishError={publishError}
          setPublishError={setPublishError}
          onPublished={(skillId) => nav(`/skills/${skillId}`)}
        />
      ) : null}
    </section>
  );
}

function Editor({ job, onChange, savingStep, setSavingStep, publishError, setPublishError, onPublished }) {
  const [draft, setDraft] = useState(job.draft);
  const [sourceCredit, setSourceCredit] = useState(job.source_credit || "");
  const [draftRev, setDraftRev] = useState(job.draft_rev);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);

  // If the server state advances (e.g. frame regen), merge in.
  useEffect(() => {
    setDraft(job.draft);
    setDraftRev(job.draft_rev);
  }, [job.draft_rev, job.draft]);

  const update = (patch) => setDraft((d) => ({ ...d, ...patch }));
  const updateStep = (n, patch) =>
    setDraft((d) => ({
      ...d,
      steps: d.steps.map((s) => (s.n === n ? { ...s, ...patch } : s)),
    }));
  const updateCheck = (id, patch) =>
    setDraft((d) => ({
      ...d,
      checks: d.checks.map((c) => (c.id === id ? { ...c, ...patch } : c)),
    }));
  const updateQuiz = (id, patch) =>
    setDraft((d) => ({
      ...d,
      quiz: d.quiz.map((q) => (q.id === id ? { ...q, ...patch } : q)),
    }));

  const addCheck = () =>
    setDraft((d) => {
      const n = (d.checks?.length || 0) + 1;
      return { ...d, checks: [...(d.checks || []), { id: `c${n}`, description: "", safety_critical: false }] };
    });
  const removeCheck = (id) =>
    setDraft((d) => ({ ...d, checks: (d.checks || []).filter((c) => c.id !== id) }));

  // Stage 1 — bounded 2..2. Add is disabled at 2+, Remove is disabled at 2-.
  const QUIZ_MIN = 2;
  const QUIZ_MAX = 2;
  const addQuiz = () =>
    setDraft((d) => {
      const existing = d.quiz || [];
      if (existing.length >= QUIZ_MAX) return d;
      // Pick next free `qN` id even if the user removed middle items.
      let n = existing.length + 1;
      const taken = new Set(existing.map((q) => q.id));
      while (taken.has(`q${n}`)) n += 1;
      return {
        ...d,
        quiz: [
          ...existing,
          { id: `q${n}`, prompt: "", choices: ["", "", ""], answer_index: 0 },
        ],
      };
    });
  const removeQuiz = (id) =>
    setDraft((d) => {
      const existing = d.quiz || [];
      if (existing.length <= QUIZ_MIN) return d;
      return { ...d, quiz: existing.filter((q) => q.id !== id) };
    });

  const save = async () => {
    setSaving(true);
    setSaveErr(null);
    try {
      const r = await api.put(`/lessons/jobs/${job.id}/draft`, {
        draft,
        source_credit: sourceCredit,
        draft_rev: draftRev,
      });
      onChange(r.data);
      setDraft(r.data.draft);
      setDraftRev(r.data.draft_rev);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setSaveErr(typeof detail === "string" ? detail : e?.message || "save failed");
    } finally {
      setSaving(false);
    }
  };

  const regenFrame = async (n) => {
    setSavingStep(true);
    try {
      // Save first so new start/end are honored.
      await save();
      await api.post(`/lessons/jobs/${job.id}/steps/${n}/frame`);
      // Reload.
      const r = await api.get(`/lessons/jobs/${job.id}`);
      onChange(r.data);
      setDraft(r.data.draft);
      setDraftRev(r.data.draft_rev);
    } catch (e) {
      setSaveErr(e?.message || "frame regen failed");
    } finally {
      setSavingStep(false);
    }
  };

  const publish = async () => {
    setPublishError(null);
    try {
      // Save pending edits before publishing.
      await save();
      const r = await api.post(`/lessons/jobs/${job.id}/publish`);
      onPublished(r.data.skill_id);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (detail && typeof detail === "object" && Array.isArray(detail.reasons)) {
        setPublishError(detail.reasons.join(" · "));
      } else {
        setPublishError(typeof detail === "string" ? detail : e?.message || "publish failed");
      }
    }
  };

  // Stage 1 — inline publish validation. Blocks the click so the user
  // sees the error next to the button INSTEAD of the Publish button
  // silently doing nothing.
  const localPublishBlockers = useMemo(() => {
    const reasons = [];
    const steps = draft?.steps || [];
    const checks = draft?.checks || [];
    const quiz = draft?.quiz || [];
    if (!steps.length) reasons.push("At least one step is required.");
    const missingFrame = steps.find((s) => !s.frame_id);
    if (missingFrame) reasons.push(`Step ${missingFrame.n} is missing a frame.`);
    if (!checks.length) reasons.push("At least one check is required.");
    if (quiz.length !== QUIZ_MIN) {
      reasons.push(`Quiz must have exactly ${QUIZ_MIN} questions (got ${quiz.length}).`);
    }
    for (const q of quiz) {
      const choices = q.choices || [];
      if (choices.length !== 3 || choices.some((c) => !String(c || "").trim())) {
        reasons.push("Each quiz question needs 3 non-empty choices.");
        break;
      }
      if (
        typeof q.answer_index !== "number" ||
        q.answer_index < 0 ||
        q.answer_index > 2
      ) {
        reasons.push("Each quiz question needs a correct answer selected.");
        break;
      }
      if (!String(q.prompt || "").trim()) {
        reasons.push("Each quiz question needs a prompt.");
        break;
      }
    }
    // Step / check text completeness.
    const emptyStep = steps.find(
      (s) => !String(s.title || "").trim() || !String(s.instruction || "").trim(),
    );
    if (emptyStep) {
      reasons.push(`Step ${emptyStep.n} needs a title and instruction.`);
    }
    const emptyCheck = checks.find((c) => !String(c.description || "").trim());
    if (emptyCheck) {
      reasons.push(`Check ${emptyCheck.id} needs a description.`);
    }
    return reasons;
  }, [draft]);

  const canPublish = localPublishBlockers.length === 0;

  return (
    <div data-testid="draft-editor" className="space-y-5">
      <div className="fs-card p-4 space-y-3">
        <label className="block space-y-1">
          <span className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
            Title
          </span>
          <input
            value={draft.title || ""}
            onChange={(e) => update({ title: e.target.value })}
            data-testid="editor-title"
            className="block w-full text-base font-ui rounded-md px-3 py-2 border bg-transparent tap"
            style={{ borderColor: "var(--fs-border)" }}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
            Source credit
          </span>
          <input
            value={sourceCredit}
            onChange={(e) => setSourceCredit(e.target.value)}
            data-testid="editor-source-credit"
            className="block w-full text-sm font-ui rounded-md px-3 py-2 border bg-transparent tap"
            style={{ borderColor: "var(--fs-border)" }}
          />
        </label>
      </div>

      <section>
        <h2 className="text-lg font-semibold mb-2">Steps</h2>
        <ol className="space-y-3" data-testid="editor-steps">
          {draft.steps.map((s) => (
            <li key={s.n} className="fs-card p-3 space-y-3" data-testid={`editor-step-${s.n}`}>
              <div className="flex gap-3">
                {s.frame_id ? (
                  <img
                    src={absoluteUrl(`/api/media/${s.frame_id}`)}
                    alt={`Step ${s.n} frame`}
                    data-testid={`editor-step-frame-${s.n}`}
                    className="w-32 h-20 object-cover rounded-md"
                  />
                ) : (
                  <div
                    data-testid={`editor-step-frame-${s.n}`}
                    className="w-32 h-20 rounded-md flex flex-col items-center justify-center text-center font-ui border border-dashed"
                    style={{
                      borderColor: "var(--fs-border)",
                      color: "var(--fs-muted)",
                      background: "transparent",
                    }}
                  >
                    <span aria-hidden="true" style={{ fontSize: "1.1rem", lineHeight: 1 }}>
                      🖼
                    </span>
                    <span className="text-[10px] mt-1">No image yet</span>
                  </div>
                )}
                <div className="flex-1 min-w-0 space-y-2">
                  <input
                    value={s.title || ""}
                    onChange={(e) => updateStep(s.n, { title: e.target.value })}
                    data-testid={`editor-step-title-${s.n}`}
                    className="block w-full font-semibold rounded-md px-2 py-1 border bg-transparent tap"
                    style={{ borderColor: "var(--fs-border)" }}
                  />
                  <div className="grid grid-cols-2 gap-2">
                    <input
                      value={fmtTime(s.start)}
                      onChange={(e) => updateStep(s.n, { start: parseTime(e.target.value) })}
                      data-testid={`editor-step-start-${s.n}`}
                      className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent tap"
                      style={{ borderColor: "var(--fs-border)" }}
                    />
                    <input
                      value={fmtTime(s.end)}
                      onChange={(e) => updateStep(s.n, { end: parseTime(e.target.value) })}
                      data-testid={`editor-step-end-${s.n}`}
                      className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent tap"
                      style={{ borderColor: "var(--fs-border)" }}
                    />
                  </div>
                </div>
              </div>
              <textarea
                value={s.instruction || ""}
                onChange={(e) => updateStep(s.n, { instruction: e.target.value })}
                rows={2}
                data-testid={`editor-step-instr-${s.n}`}
                className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent"
                style={{ borderColor: "var(--fs-border)" }}
              />
              <button
                type="button"
                onClick={() => regenFrame(s.n)}
                disabled={savingStep}
                data-testid={`editor-regen-${s.n}`}
                className="tap px-3 text-xs font-ui rounded-full border"
                style={{ borderColor: "var(--fs-border)" }}
              >
                Regenerate frame
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">Checks</h2>
          <button
            type="button"
            onClick={addCheck}
            data-testid="editor-add-check"
            className="tap px-3 text-xs font-ui rounded-full border"
            style={{ borderColor: "var(--fs-border)" }}
          >
            + Add check
          </button>
        </div>
        <ul className="fs-card fs-divider" data-testid="editor-checks">
          {draft.checks.map((c) => (
            <li key={c.id} className="px-3 py-3 space-y-2" data-testid={`editor-check-${c.id}`}>
              <input
                value={c.description || ""}
                onChange={(e) => updateCheck(c.id, { description: e.target.value })}
                data-testid={`editor-check-desc-${c.id}`}
                className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent tap"
                style={{ borderColor: "var(--fs-border)" }}
              />
              <div className="flex items-center justify-between">
                <label className="text-xs font-ui inline-flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={!!c.safety_critical}
                    onChange={(e) => updateCheck(c.id, { safety_critical: e.target.checked })}
                    data-testid={`editor-check-safety-${c.id}`}
                  />
                  Safety-critical
                </label>
                <button
                  type="button"
                  onClick={() => removeCheck(c.id)}
                  data-testid={`editor-check-remove-${c.id}`}
                  className="text-xs font-ui"
                  style={{ color: "var(--fs-fail)" }}
                >
                  Remove
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section>
        <div className="flex items-center justify-between mb-2">
          <h2 className="text-lg font-semibold">
            Quiz
            <span
              className="ml-2 text-xs font-ui"
              style={{
                color:
                  draft.quiz.length === QUIZ_MIN
                    ? "var(--fs-muted)"
                    : "var(--fs-fail)",
              }}
              data-testid="editor-quiz-count"
            >
              {draft.quiz.length} / {QUIZ_MIN}
            </span>
          </h2>
          <button
            type="button"
            onClick={addQuiz}
            disabled={draft.quiz.length >= QUIZ_MAX}
            data-testid="editor-add-quiz"
            className="tap px-3 text-xs font-ui rounded-full border"
            style={{
              borderColor: "var(--fs-border)",
              opacity: draft.quiz.length >= QUIZ_MAX ? 0.45 : 1,
            }}
          >
            + Add question
          </button>
        </div>
        <ul className="space-y-3" data-testid="editor-quiz">
          {draft.quiz.map((q) => (
            <li key={q.id} className="fs-card p-3 space-y-2" data-testid={`editor-quiz-${q.id}`}>
              <div className="flex items-start gap-2">
                <input
                  value={q.prompt || ""}
                  onChange={(e) => updateQuiz(q.id, { prompt: e.target.value })}
                  data-testid={`editor-quiz-prompt-${q.id}`}
                  className="block flex-1 text-sm font-ui rounded-md px-2 py-1 border bg-transparent tap"
                  style={{ borderColor: "var(--fs-border)" }}
                />
                <button
                  type="button"
                  onClick={() => removeQuiz(q.id)}
                  disabled={draft.quiz.length <= QUIZ_MIN}
                  data-testid={`editor-quiz-remove-${q.id}`}
                  className="text-xs font-ui tap px-2"
                  style={{
                    color: "var(--fs-fail)",
                    opacity: draft.quiz.length <= QUIZ_MIN ? 0.4 : 1,
                  }}
                  title={
                    draft.quiz.length <= QUIZ_MIN
                      ? `At least ${QUIZ_MIN} questions required`
                      : "Remove question"
                  }
                >
                  Remove
                </button>
              </div>
              <div className="space-y-1">
                {(q.choices || []).slice(0, 3).map((opt, i) => (
                  <label key={i} className="flex items-center gap-2">
                    <input
                      type="radio"
                      name={`quiz-${q.id}-ans`}
                      checked={q.answer_index === i}
                      onChange={() => updateQuiz(q.id, { answer_index: i })}
                      data-testid={`editor-quiz-radio-${q.id}-${i}`}
                    />
                    <span
                      className="font-ui text-xs"
                      style={{ color: "var(--fs-muted)", minWidth: "1ch" }}
                    >
                      {i + 1}.
                    </span>
                    <input
                      value={opt}
                      onChange={(e) => {
                        const choices = [...q.choices];
                        choices[i] = e.target.value;
                        updateQuiz(q.id, { choices });
                      }}
                      data-testid={`editor-quiz-opt-${q.id}-${i}`}
                      className="block flex-1 text-sm font-ui rounded-md px-2 py-1 border bg-transparent tap"
                      style={{ borderColor: "var(--fs-border)" }}
                    />
                  </label>
                ))}
              </div>
            </li>
          ))}
          {draft.quiz.length === 0 ? (
            <li
              className="fs-card px-4 py-3 text-xs font-ui"
              data-testid="editor-quiz-empty"
              style={{ color: "var(--fs-muted)" }}
            >
              No quiz questions yet. Publish requires exactly {QUIZ_MIN}.
            </li>
          ) : null}
        </ul>
      </section>

      {(job.problems || []).length > 0 ? (
        <ul className="fs-card fs-divider" data-testid="editor-problems">
          {job.problems.map((p, i) => (
            <li
              key={i}
              className="px-3 py-2 text-xs font-ui"
              style={{ color: p.blocking ? "var(--fs-fail)" : "var(--fs-warn)" }}
              data-testid={`editor-problem-${i}`}
            >
              <strong>{p.where}:</strong> {p.message}
            </li>
          ))}
        </ul>
      ) : null}

      {saveErr ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }} data-testid="editor-save-error">
          {saveErr}
        </p>
      ) : null}
      {publishError ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }} data-testid="editor-publish-error">
          {publishError}
        </p>
      ) : null}

      {/* Stage 1 — inline validation surfaced NEXT to the Publish button
          so the user never sees it silently refuse. */}
      {localPublishBlockers.length > 0 ? (
        <ul
          className="fs-card fs-divider"
          data-testid="editor-publish-blockers"
        >
          {localPublishBlockers.map((r, i) => (
            <li
              key={i}
              className="px-3 py-2 text-xs font-ui"
              style={{ color: "var(--fs-fail)" }}
              data-testid={`editor-publish-blocker-${i}`}
            >
              {r}
            </li>
          ))}
        </ul>
      ) : null}

      <div className="flex gap-3">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          data-testid="editor-save-btn"
          className="tap px-4 rounded-full text-sm font-ui border"
          style={{ borderColor: "var(--fs-border)" }}
        >
          {saving ? "Saving…" : "Save"}
        </button>
        <button
          type="button"
          onClick={publish}
          disabled={!canPublish || saving}
          data-testid="editor-publish-btn"
          className="tap px-4 rounded-full text-sm font-ui flex-1"
          style={{
            background: "var(--fs-primary)",
            color: "var(--fs-primary-fg)",
            opacity: canPublish && !saving ? 1 : 0.55,
          }}
          title={canPublish ? "Publish" : "Fix the issues above first"}
        >
          Publish
        </button>
      </div>
    </div>
  );
}
