import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { useCaregiver } from "@/shell/CaregiverLayout";

/* Status chip labels per language, keyed by the `status` string the
   /api/lessons/caregiver endpoint returns. Every status (including
   `todo`) has a label; the chip is always rendered. */
const CHIP_LABELS = {
  en: {
    cleared: "Cleared",
    awaiting_signoff: "Waiting for sign-off",
    practice_video_next: "Practice video next",
    in_progress: "In progress",
    todo: "Not started",
  },
  es: {
    cleared: "Aprobado",
    awaiting_signoff: "Esperando firma",
    practice_video_next: "Falta el video",
    in_progress: "En progreso",
    todo: "Sin comenzar",
  },
  tl: {
    cleared: "Natapos na",
    awaiting_signoff: "Hinihintay ang sign-off",
    practice_video_next: "Susunod ang practice video",
    in_progress: "Kasalukuyang ginagawa",
    todo: "Hindi pa nasimulan",
  },
};

function chipClass(status) {
  if (status === "cleared") return "fs-chip-pass";
  if (status === "awaiting_signoff" || status === "practice_video_next") return "fs-chip-warn";
  if (status === "todo") return "fs-chip-muted";
  return "";
}

export default function CaregiverLessonsPage() {
  const { caregiver, code } = useCaregiver();
  const navigate = useNavigate();
  const [state, setState] = useState({ status: "loading" });
  const [opening, setOpening] = useState(null); // skill_id being opened
  const [openErr, setOpenErr] = useState(null);

  const load = () =>
    api
      .get(`/lessons/caregiver/${caregiver.id}`)
      .then((r) => setState({ status: "ok", data: r.data }))
      .catch((e) =>
        setState({ status: "error", error: e?.message || "failed" }),
      );

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
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
  const lang = caregiver.language || "en";
  const chipLabels = CHIP_LABELS[lang] || CHIP_LABELS.en;

  const openLesson = async (skillId) => {
    setOpening(skillId);
    setOpenErr(null);
    try {
      // Server-side injects a bot message that opens the lesson — same
      // path the FSM takes when the caregiver taps a number in the chat
      // menu. We don't duplicate state here (Item F).
      await api.post("/channel/open-lesson", {
        caregiver_id: caregiver.id,
        skill_id: skillId,
      });
      // Caregiver chat route is `/c/:code` (no `/chat` subpath) — see
      // backend/features/channel/routes.js.
      navigate(`/c/${code}`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setOpenErr(typeof detail === "string" ? detail : e?.message || "failed");
      setOpening(null);
    }
  };

  const rowButton = (s) => (
    <button
      key={s.id}
      type="button"
      onClick={() => openLesson(s.id)}
      disabled={opening != null}
      data-testid={`caregiver-lesson-row-${s.id}`}
      className="w-full tap text-left px-4 py-3 flex items-center justify-between gap-3"
      style={{ opacity: opening && opening !== s.id ? 0.55 : 1 }}
    >
      <div className="min-w-0 flex-1">
        <div className="font-semibold leading-snug">{s.title}</div>
        <div
          className="text-xs font-ui mt-0.5"
          style={{ color: "var(--fs-muted)" }}
        >
          {s.step_count} steps
        </div>
      </div>
      {chipLabels[s.status] ? (
        <span
          className={`fs-chip whitespace-nowrap ${chipClass(s.status)}`}
          data-testid={`caregiver-lesson-chip-${s.id}`}
        >
          {chipLabels[s.status]}
        </span>
      ) : null}
    </button>
  );

  return (
    <div className="px-5 py-6 space-y-6" data-testid="caregiver-lessons-page">
      <h2 className="text-xl font-semibold">Lessons</h2>

      {openErr ? (
        <p
          className="text-sm"
          style={{ color: "var(--fs-fail)" }}
          data-testid="caregiver-lessons-open-error"
        >
          {openErr}
        </p>
      ) : null}

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
              <li key={s.id}>{rowButton(s)}</li>
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
              <li key={s.id}>{rowButton(s)}</li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
