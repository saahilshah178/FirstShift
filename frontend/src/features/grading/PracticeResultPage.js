import React, { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, absoluteUrl } from "@/api";
import { useCaregiver } from "@/shell/CaregiverLayout";

const POLL_MS = 3000;

const RESULT_LABEL = {
  pass: "✓",
  fail: "✗",
  unclear: "?",
};

const RESULT_CHIP = {
  pass: "fs-chip fs-chip-pass",
  fail: "fs-chip fs-chip-fail",
  unclear: "fs-chip fs-chip-warn",
};

function fmtTime(seconds) {
  if (seconds == null) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds - m * 60;
  return `${m}:${s.toFixed(1).padStart(4, "0")}`;
}

export default function PracticeResultPage() {
  const { attemptId, code } = useParams();
  const { caregiver } = useCaregiver();
  const [attempt, setAttempt] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let timer;
    let aborted = false;

    async function poll() {
      try {
        const r = await api.get(`/grading/attempts/${attemptId}`);
        if (aborted) return;
        setAttempt(r.data);
        if (r.data.status === "grading") {
          timer = setTimeout(poll, POLL_MS);
        }
      } catch (e) {
        if (aborted) return;
        setErr(e?.response?.data?.detail || e.message);
      }
    }
    poll();
    return () => {
      aborted = true;
      if (timer) clearTimeout(timer);
    };
  }, [attemptId]);

  async function regrade() {
    try {
      await api.post(`/grading/attempts/${attemptId}/regrade`);
      setAttempt(null);
      setErr(null);
      // trigger a re-poll
      const r = await api.get(`/grading/attempts/${attemptId}`);
      setAttempt(r.data);
    } catch (e) {
      setErr(e?.response?.data?.detail || e.message);
    }
  }

  if (err) {
    return (
      <div className="px-5 py-6" data-testid="practice-result-error">
        <p style={{ color: "var(--fs-fail)" }}>{err}</p>
      </div>
    );
  }

  if (!attempt) {
    return (
      <div className="px-5 py-6" data-testid="practice-result-loading">
        <p className="font-ui text-sm" style={{ color: "var(--fs-muted)" }}>
          Loading…
        </p>
      </div>
    );
  }

  const sentBackNote =
    attempt.signoff?.decision === "send_back" ? attempt.signoff.note : null;

  return (
    <div className="px-5 py-6 space-y-5" data-testid="practice-result">
      <Link
        to={`/c/${code}/practice`}
        className="font-ui text-sm underline"
        data-testid="practice-result-back"
      >
        ← {attempt.skill_title}
      </Link>

      {attempt.status === "grading" ? (
        <div
          className="fs-card p-5 text-center"
          data-testid="practice-result-grading"
        >
          <div
            className="animate-pulse text-xl font-semibold"
            style={{ color: "var(--fs-primary)" }}
          >
            Grading…
          </div>
          <p
            className="font-ui text-sm mt-2"
            style={{ color: "var(--fs-muted)" }}
          >
            This usually takes under a minute.
          </p>
        </div>
      ) : null}

      {attempt.status === "retake_required" ? (
        <div
          className="fs-card p-5"
          data-testid="practice-result-retake"
          style={{ background: "var(--fs-accent)" }}
        >
          <h3 className="text-xl font-semibold">Retake needed</h3>
          <p className="mt-2 font-ui text-sm">
            {attempt.message_for_caregiver ||
              "We couldn't see a key step clearly. Please re-film."}
          </p>
          <div className="mt-3 flex flex-wrap gap-2">
            {attempt.checks
              .filter(
                (c) => c.safety_critical && c.result !== "pass",
              )
              .map((c) => (
                <span
                  key={c.id}
                  className="fs-chip fs-chip-warn"
                  data-testid={`practice-result-retake-chip-${c.id}`}
                >
                  {c.description}
                </span>
              ))}
          </div>
          <Link
            to={`/c/${code}/practice`}
            className="mt-4 inline-block tap px-4 rounded-full font-ui text-sm"
            style={{
              background: "var(--fs-primary)",
              color: "var(--fs-primary-fg)",
            }}
            data-testid="practice-result-refilm"
          >
            Re-film
          </Link>
        </div>
      ) : null}

      {attempt.status === "grading_error" ? (
        <div
          className="fs-card p-5"
          data-testid="practice-result-error-state"
        >
          <h3 className="text-xl font-semibold">Grading hiccup</h3>
          <p
            className="mt-2 font-ui text-sm"
            style={{ color: "var(--fs-muted)" }}
          >
            {attempt.error || "Something went wrong while grading."}
          </p>
          <button
            type="button"
            onClick={regrade}
            data-testid="practice-result-regrade"
            className="mt-3 tap px-4 rounded-full font-ui text-sm"
            style={{
              background: "var(--fs-primary)",
              color: "var(--fs-primary-fg)",
            }}
          >
            Grade again
          </button>
        </div>
      ) : null}

      {sentBackNote ? (
        <div
          className="fs-card p-5"
          data-testid="practice-result-sent-back"
          style={{ borderColor: "var(--fs-primary)" }}
        >
          <h3 className="text-sm font-semibold uppercase tracking-wide">
            Sent back by {attempt.signoff.signer}
          </h3>
          <p className="mt-2 font-ui text-sm">{sentBackNote}</p>
        </div>
      ) : null}

      {["ready_to_sign", "needs_practice"].includes(attempt.status) ? (
        <>
          <div className="fs-card p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold uppercase tracking-wide">
                {attempt.status === "ready_to_sign"
                  ? "Ready to sign"
                  : "Needs practice"}
              </h3>
              {attempt.graded_once ? (
                <span className="fs-chip" data-testid="practice-result-graded-once">
                  graded once
                </span>
              ) : null}
            </div>
            {attempt.message_for_caregiver ? (
              <p className="mt-2 font-ui text-sm">
                {attempt.message_for_caregiver}
              </p>
            ) : null}
          </div>
          <ul
            className="fs-card fs-divider"
            data-testid="practice-result-checks"
          >
            {attempt.checks.map((c) => (
              <li
                key={c.id}
                className="px-4 py-3"
                data-testid={`practice-check-${c.id}`}
              >
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
                  <div className="flex flex-col items-end gap-1">
                    <span className={RESULT_CHIP[c.result] || "fs-chip"}>
                      {RESULT_LABEL[c.result] || "?"} {c.result}
                    </span>
                    <span
                      className="font-ui text-xs tabular-nums"
                      style={{ color: "var(--fs-muted)" }}
                    >
                      {fmtTime(c.time)}
                    </span>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </>
      ) : null}
    </div>
  );
}
