import React, { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, absoluteUrl } from "@/api";
import { useRole, canSignoff } from "@/hooks/useRole";

const RESULT_CHIP = {
  pass: "fs-chip fs-chip-pass",
  fail: "fs-chip fs-chip-fail",
  unclear: "fs-chip fs-chip-warn",
};

const SIGNER_KEY = "firstshift.grading.signer_name";

function fmtClipTime(seconds) {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export default function SignoffDetailPage() {
  const { attemptId } = useParams();
  const navigate = useNavigate();
  const videoRef = useRef(null);
  const role = useRole();
  const canSign = canSignoff(role);
  const [attempt, setAttempt] = useState(null);
  const [err, setErr] = useState(null);
  const [signer, setSigner] = useState(
    () => localStorage.getItem(SIGNER_KEY) || "",
  );
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [actionErr, setActionErr] = useState(null);

  useEffect(() => {
    localStorage.setItem(SIGNER_KEY, signer);
  }, [signer]);

  useEffect(() => {
    api
      .get(`/grading/attempts/${attemptId}`)
      .then((r) => setAttempt(r.data))
      .catch((e) => setErr(e?.response?.data?.detail || e.message));
  }, [attemptId]);

  const markers = useMemo(() => {
    if (!attempt) return [];
    return attempt.checks
      .map((c, i) =>
        c.result === "fail" || c.result === "unclear"
          ? { i, c }
          : null,
      )
      .filter(Boolean);
  }, [attempt]);

  const hasFail = useMemo(
    () => !!attempt?.checks?.some((c) => c.result === "fail"),
    [attempt],
  );

  async function act(decision) {
    if (!signer.trim()) {
      setActionErr("Signer name is required.");
      return;
    }
    if (decision === "send_back" && !note.trim()) {
      setActionErr("Note is required when sending back.");
      return;
    }
    if (decision === "approve" && hasFail && !note.trim()) {
      setActionErr("Note is required when overriding a failed verdict.");
      return;
    }
    setSubmitting(true);
    setActionErr(null);
    try {
      await api.post(`/grading/attempts/${attemptId}/signoff`, {
        decision,
        signer: signer.trim(),
        signer_role: role,
        note: note.trim(),
      });
      navigate("/signoff");
    } catch (e) {
      setActionErr(e?.response?.data?.detail || e.message);
    } finally {
      setSubmitting(false);
    }
  }

  function seekTo(seconds) {
    const v = videoRef.current;
    if (!v) return;
    const target = Math.max(0, seconds - 1);
    v.currentTime = target;
    v.play().catch(() => {});
  }

  if (err) {
    return (
      <section className="space-y-3" data-testid="signoff-detail-error">
        <Link to="/signoff" className="font-ui text-sm underline">
          ← Sign-off
        </Link>
        <p style={{ color: "var(--fs-fail)" }}>{err}</p>
      </section>
    );
  }
  if (!attempt) {
    return (
      <p className="font-ui text-sm" style={{ color: "var(--fs-muted)" }}>
        Loading…
      </p>
    );
  }

  const clipUrl = absoluteUrl(`/api/media/${attempt.clip_id}`);
  const unsignable = !["ready_to_sign", "needs_practice"].includes(
    attempt.status,
  );
  const alreadyReviewed = attempt.reviewed;

  return (
    <section
      className="space-y-5"
      data-testid="signoff-detail-page"
      data-attempt-id={attemptId}
    >
      <Link to="/signoff" className="font-ui text-sm underline">
        ← Sign-off
      </Link>
      <header>
        <h1 className="text-2xl font-semibold">{attempt.caregiver_name}</h1>
        <p
          className="text-sm font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          {attempt.skill_title}
        </p>
      </header>

      <video
        ref={videoRef}
        src={clipUrl}
        controls
        playsInline
        className="w-full rounded-lg border"
        style={{ borderColor: "var(--fs-border)" }}
        data-testid="signoff-video"
      />

      {markers.length > 0 ? (
        <div data-testid="signoff-markers" className="flex flex-wrap gap-2">
          {markers.map(({ i, c }) => (
            <button
              key={c.id}
              type="button"
              onClick={() => seekTo(c.time ?? 0)}
              className="fs-chip fs-chip-warn tap"
              data-testid={`signoff-marker-${c.id}`}
              title={c.description}
            >
              {fmtClipTime(c.time)} · {c.result}
            </button>
          ))}
        </div>
      ) : null}

      <ul className="fs-card fs-divider" data-testid="signoff-checks">
        {attempt.checks.map((c) => (
          <li key={c.id} className="px-4 py-3">
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1">
                <div className="font-semibold">{c.description}</div>
                {c.note ? (
                  <div
                    className="font-ui text-xs mt-1"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {c.note}
                  </div>
                ) : null}
              </div>
              <span className={RESULT_CHIP[c.result] || "fs-chip"}>
                {c.result}
              </span>
            </div>
          </li>
        ))}
      </ul>

      {unsignable || alreadyReviewed ? (
        <div
          className="fs-card p-4"
          style={{ background: "var(--fs-accent)" }}
          data-testid="signoff-unsignable"
        >
          <p className="font-ui text-sm">
            {alreadyReviewed
              ? `Already ${attempt.signoff?.decision ?? "reviewed"} by ${
                  attempt.signoff?.signer ?? "someone"
                }.`
              : `Current status (${attempt.status}) is not signable.`}
          </p>
        </div>
      ) : !canSign ? (
        <div
          className="fs-card p-4"
          data-testid="signoff-role-gate"
          style={{ background: "var(--fs-accent)" }}
        >
          <p className="font-ui text-sm">
            Switch to Care Manager to approve or send back this attempt.
          </p>
        </div>
      ) : (
        <div className="fs-card p-4 space-y-3" data-testid="signoff-actions">
          <label className="block">
            <span
              className="text-xs uppercase tracking-wide font-ui"
              style={{ color: "var(--fs-muted)" }}
            >
              Signer name
            </span>
            <input
              type="text"
              value={signer}
              onChange={(e) => setSigner(e.target.value)}
              data-testid="signoff-signer"
              placeholder="Your name, title"
              className="mt-1 w-full tap px-3 rounded-lg border font-ui text-sm"
              style={{
                borderColor: "var(--fs-border)",
                background: "var(--fs-surface)",
              }}
            />
            {role ? (
              <span
                className="font-ui text-[11px] mt-1 block"
                style={{ color: "var(--fs-muted)" }}
              >
                role: {role}
              </span>
            ) : null}
          </label>
          <label className="block">
            <span
              className="text-xs uppercase tracking-wide font-ui"
              style={{ color: "var(--fs-muted)" }}
            >
              Note{" "}
              {hasFail
                ? "(required to override failed checks)"
                : "(required for Send back)"}
            </span>
            <textarea
              rows={3}
              value={note}
              onChange={(e) => setNote(e.target.value)}
              data-testid="signoff-note"
              className="mt-1 w-full rounded-lg border font-ui text-sm p-3"
              style={{
                borderColor: "var(--fs-border)",
                background: "var(--fs-surface)",
              }}
            />
          </label>
          {hasFail ? (
            <p
              className="font-ui text-xs"
              style={{ color: "var(--fs-warn)" }}
              data-testid="signoff-override-warning"
            >
              This attempt has at least one failed check. Approving will be
              recorded as an override.
            </p>
          ) : null}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => act("approve")}
              disabled={submitting}
              data-testid="signoff-approve"
              className="flex-1 tap rounded-full font-ui text-sm font-semibold disabled:opacity-50"
              style={{
                background: "var(--fs-primary)",
                color: "var(--fs-primary-fg)",
              }}
            >
              Approve
            </button>
            <button
              type="button"
              onClick={() => act("send_back")}
              disabled={submitting}
              data-testid="signoff-send-back"
              className="flex-1 tap rounded-full font-ui text-sm font-semibold border disabled:opacity-50"
              style={{ borderColor: "var(--fs-primary)" }}
            >
              Send back
            </button>
          </div>
          {actionErr ? (
            <p
              className="font-ui text-xs"
              style={{ color: "var(--fs-fail)" }}
              data-testid="signoff-action-error"
            >
              {actionErr}
            </p>
          ) : null}
        </div>
      )}
    </section>
  );
}
