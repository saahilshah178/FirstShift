import React, { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, absoluteUrl } from "@/api";
import { useCaps } from "@/hooks/useRole";

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

// Stage 3 — plan-item status chips (distinct from the attempt-latest chips above).
const PLAN_STATUS_CHIP = {
  not_started: "fs-chip-muted",
  practicing: "fs-chip-warn",
  cleared: "fs-chip-pass",
  refresher: "fs-chip-fail",
};
const PLAN_STATUS_LABEL = {
  not_started: "Not started",
  practicing: "Practicing",
  cleared: "Cleared",
  refresher: "Refresher",
};

export default function CompetencyDetailPage() {
  const { caregiverId } = useParams();
  const { can } = useCaps();
  const canNearMiss = can.nearMiss;
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  const [expanded, setExpanded] = useState({});
  const [plan, setPlan] = useState(null);
  const [drafts, setDrafts] = useState([]);
  const [nearMiss, setNearMiss] = useState({ open: false, skill_id: "", description: "" });
  const [nearMissErr, setNearMissErr] = useState(null);

  const loadAll = async () => {
    try {
      const [compResp, planResp, draftResp] = await Promise.all([
        api.get(`/grading/competency/${caregiverId}`),
        api.get(`/plans/caregiver/${caregiverId}`),
        api.get(`/plans/caregiver/${caregiverId}/refresher-drafts`),
      ]);
      setData(compResp.data);
      setPlan(planResp.data);
      setDrafts(draftResp.data.drafts || []);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    }
  };

  useEffect(() => {
    // Stage 4-G: shared GET dedupe in api.js collapses the StrictMode
    // double-mount into one request per endpoint.
    loadAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [caregiverId]);

  const submitNearMiss = async () => {
    setNearMissErr(null);
    try {
      await api.post(`/plans/caregiver/${caregiverId}/near-miss`, {
        skill_id: nearMiss.skill_id,
        description: nearMiss.description,
      });
      setNearMiss({ open: false, skill_id: "", description: "" });
      await loadAll();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setNearMissErr(
        typeof detail === "string"
          ? detail
          : detail?.reason === "role_not_allowed"
          ? `Only ${(detail.allowed || []).join(", ")} can report a near-miss.`
          : e?.message || "failed",
      );
    }
  };

  const updateDraft = async (draftId, text) => {
    try {
      await api.put(`/plans/refresher-drafts/${draftId}`, { text });
      await loadAll();
    } catch {
      /* let the user retry */
    }
  };
  const sendDraft = async (draftId) => {
    try {
      await api.post(`/plans/refresher-drafts/${draftId}/send`);
      await loadAll();
    } catch {
      /* keep draft on screen; show no silent success */
    }
  };
  const discardDraft = async (draftId) => {
    try {
      await api.delete(`/plans/refresher-drafts/${draftId}`);
      await loadAll();
    } catch {
      /* let the user retry */
    }
  };

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

      {/* Stage 3 — Plan with mode + status badges, verify-because,
          refresher trail. Rendered above the attempts list so the
          Care Manager sees priorities before history. */}
      {plan ? (
        <section
          className="fs-card p-4 space-y-3"
          data-testid="competency-plan"
        >
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold">
              Plan ({plan.cleared_count}/{plan.total} cleared)
            </h2>
            {canNearMiss && plan.items.some((i) => i.status === "cleared") ? (
              <button
                type="button"
                onClick={() =>
                  setNearMiss({
                    open: true,
                    skill_id:
                      plan.items.find((i) => i.status === "cleared")?.skill_id ||
                      "",
                    description: "",
                  })
                }
                data-testid="competency-near-miss-btn"
                className="tap px-3 text-xs font-ui rounded-full border"
                style={{ borderColor: "var(--fs-border)", color: "var(--fs-fail)" }}
                title="Report a near-miss on a cleared skill"
              >
                Report near-miss
              </button>
            ) : null}
          </div>
          <ul className="fs-divider" data-testid="competency-plan-list">
            {plan.items.map((item) => (
              <li
                key={item.skill_id}
                className="py-2 flex items-start justify-between gap-3"
                data-testid={`competency-plan-row-${item.skill_id}`}
              >
                <div className="min-w-0 flex-1">
                  <div className="font-semibold">{item.title}</div>
                  {item.mode === "verify" && item.verified_because ? (
                    <div
                      className="text-xs font-ui mt-0.5"
                      data-testid={`competency-plan-verified-${item.skill_id}`}
                      style={{ color: "var(--fs-muted)" }}
                    >
                      Verified because: {item.verified_because}
                    </div>
                  ) : null}
                  {item.status === "refresher" && item.refresher_at ? (
                    <div
                      className="text-xs font-ui mt-0.5"
                      data-testid={`competency-plan-refresher-${item.skill_id}`}
                      style={{ color: "var(--fs-warn)" }}
                    >
                      Reopened after near-miss on{" "}
                      {fmtDate(item.refresher_at)}
                    </div>
                  ) : null}
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <span
                    className={`fs-chip ${item.mode === "verify" ? "fs-chip-warn" : "fs-chip-muted"}`}
                    data-testid={`competency-plan-mode-${item.skill_id}`}
                  >
                    {item.mode === "verify" ? "Verify" : "Learn"}
                  </span>
                  <span
                    className={`fs-chip ${PLAN_STATUS_CHIP[item.status] || ""}`}
                    data-testid={`competency-plan-status-${item.skill_id}`}
                  >
                    {PLAN_STATUS_LABEL[item.status] || item.status}
                  </span>
                </div>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      {/* Draft refresher messages — Care Manager edits, sends, or discards. */}
      {drafts.length > 0 ? (
        <section
          className="fs-card p-4 space-y-3"
          data-testid="competency-refresher-drafts"
        >
          <h2 className="text-lg font-semibold">
            Draft refresher message
            {drafts.length > 1 ? "s" : ""}
          </h2>
          {drafts.map((d) => (
            <RefresherDraft
              key={d.id}
              draft={d}
              onSave={(text) => updateDraft(d.id, text)}
              onSend={() => sendDraft(d.id)}
              onDiscard={() => discardDraft(d.id)}
              testid={`competency-refresher-draft-${d.id}`}
            />
          ))}
        </section>
      ) : null}

      {nearMiss.open ? (
        <NearMissDialog
          plan={plan}
          state={nearMiss}
          setState={setNearMiss}
          onSubmit={submitNearMiss}
          onClose={() => setNearMiss({ open: false, skill_id: "", description: "" })}
          error={nearMissErr}
        />
      ) : null}

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
                          <>
                            {" "}
                            <span
                              className="fs-chip fs-chip-warn"
                              data-testid={`competency-override-${row.skill.id}`}
                            >
                              Override
                            </span>
                          </>
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


function RefresherDraft({ draft, onSave, onSend, onDiscard, testid }) {
  const [text, setText] = useState(draft.text || "");
  const [sending, setSending] = useState(false);
  const dirty = text !== (draft.text || "");

  const handleSend = async () => {
    setSending(true);
    try {
      if (dirty) await onSave(text);
      await onSend();
    } finally {
      setSending(false);
    }
  };

  return (
    <div
      className="rounded-xl p-3 border"
      style={{ borderColor: "var(--fs-border)" }}
      data-testid={testid}
    >
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => {
          if (dirty) onSave(text);
        }}
        rows={4}
        data-testid={`${testid}-textarea`}
        className="w-full rounded-md px-2 py-2 font-ui text-sm resize-y"
        style={{
          background: "var(--fs-surface)",
          color: "var(--fs-fg)",
          border: "1px solid var(--fs-border)",
          minHeight: 80,
        }}
      />
      <div
        className="text-xs font-ui mt-1"
        style={{ color: "var(--fs-muted)" }}
      >
        Not yet sent to the caregiver.
      </div>
      <div className="flex gap-2 mt-2">
        <button
          type="button"
          onClick={handleSend}
          disabled={sending || !text.trim()}
          data-testid={`${testid}-send-btn`}
          className="tap px-4 rounded-full text-sm font-ui"
          style={{
            background: "var(--fs-primary)",
            color: "var(--fs-primary-fg)",
            opacity: sending || !text.trim() ? 0.5 : 1,
          }}
        >
          {sending ? "Sending…" : "Send"}
        </button>
        <button
          type="button"
          onClick={onDiscard}
          disabled={sending}
          data-testid={`${testid}-discard-btn`}
          className="tap px-4 rounded-full text-sm font-ui border"
          style={{
            borderColor: "var(--fs-border)",
            color: "var(--fs-muted)",
          }}
        >
          Discard
        </button>
      </div>
    </div>
  );
}

function NearMissDialog({ plan, state, setState, onSubmit, onClose, error }) {
  const items = (plan && plan.items) || [];
  const choices = items.filter((i) => i.status === "cleared");
  return (
    <div
      role="dialog"
      aria-label="Report near-miss"
      className="fixed inset-0 z-40 flex items-end sm:items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.4)" }}
      data-testid="near-miss-dialog"
      onClick={onClose}
    >
      <div
        className="fs-card w-full sm:max-w-md p-4 space-y-3"
        style={{ background: "var(--fs-surface)" }}
        onClick={(e) => e.stopPropagation()}
      >
        <header className="flex items-center justify-between">
          <h3 className="text-lg font-semibold">Report near-miss</h3>
          <button
            type="button"
            onClick={onClose}
            data-testid="near-miss-close-btn"
            className="tap text-sm font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            Cancel
          </button>
        </header>
        <p
          className="text-xs font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          Pick a skill, describe what happened. The caregiver's clearance
          is pulled instantly; a draft refresher message appears for your
          review before anything reaches their chat.
        </p>
        <label
          className="block text-xs font-ui uppercase tracking-wide"
          style={{ color: "var(--fs-muted)" }}
        >
          Skill
        </label>
        <select
          value={state.skill_id}
          onChange={(e) => setState((s) => ({ ...s, skill_id: e.target.value }))}
          data-testid="near-miss-skill"
          className="w-full rounded-md px-2 py-2 text-sm font-ui"
          style={{
            background: "var(--fs-surface)",
            border: "1px solid var(--fs-border)",
            color: "var(--fs-fg)",
          }}
        >
          {choices.map((i) => (
            <option key={i.skill_id} value={i.skill_id}>
              {i.title}
            </option>
          ))}
        </select>
        <label
          className="block text-xs font-ui uppercase tracking-wide"
          style={{ color: "var(--fs-muted)" }}
        >
          What happened?
        </label>
        <textarea
          value={state.description}
          onChange={(e) =>
            setState((s) => ({ ...s, description: e.target.value }))
          }
          rows={4}
          placeholder="Short description for the audit log."
          data-testid="near-miss-description"
          className="w-full rounded-md px-2 py-2 text-sm font-ui"
          style={{
            background: "var(--fs-surface)",
            border: "1px solid var(--fs-border)",
            color: "var(--fs-fg)",
            minHeight: 90,
          }}
        />
        {error ? (
          <p
            className="text-sm"
            style={{ color: "var(--fs-fail)" }}
            data-testid="near-miss-error"
          >
            {error}
          </p>
        ) : null}
        <div className="flex gap-2">
          <button
            type="button"
            onClick={onSubmit}
            disabled={!state.skill_id || !state.description.trim()}
            data-testid="near-miss-submit-btn"
            className="tap flex-1 px-4 rounded-full text-sm font-ui"
            style={{
              background: "var(--fs-fail)",
              color: "white",
              opacity:
                !state.skill_id || !state.description.trim() ? 0.5 : 1,
            }}
          >
            Pull clearance + draft refresher
          </button>
        </div>
      </div>
    </div>
  );
}

