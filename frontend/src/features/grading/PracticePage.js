import React, { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "@/api";
import { useCaregiver } from "@/shell/CaregiverLayout";

const MAX_DURATION = 45;
const MIN_DURATION = 3;

/* Stage 2 — status chip labels per language. Same source of truth agency
   uses (/api/lessons/caregiver). "todo" renders no chip. */
const CHIP_LABELS = {
  en: {
    cleared: "Cleared",
    awaiting_signoff: "Waiting for sign-off",
    practice_video_next: "Practice video next",
    in_progress: "In progress",
  },
  es: {
    cleared: "Aprobado",
    awaiting_signoff: "Esperando firma",
    practice_video_next: "Falta el video",
    in_progress: "En progreso",
  },
  tl: {
    cleared: "Natapos na",
    awaiting_signoff: "Hinihintay ang sign-off",
    practice_video_next: "Susunod ang practice video",
    in_progress: "Kasalukuyang ginagawa",
  },
};

function chipClass(status) {
  if (status === "cleared") return "fs-chip-pass";
  if (status === "awaiting_signoff" || status === "practice_video_next") return "fs-chip-warn";
  return "";
}

const T = {
  en: {
    title: "Practice",
    pick: "Pick a skill to film",
    steps: "Steps",
    record: "Record a clip",
    choose: "Choose video file",
    rules: `${MIN_DURATION}-${MAX_DURATION}s · must be a real video file`,
    uploading: "Uploading…",
    tooLong: (d) =>
      `Clip is ${d.toFixed(1)}s. Please film under ${MAX_DURATION}s.`,
    tooShort: (d) =>
      `Clip is ${d.toFixed(1)}s. Please film at least ${MIN_DURATION}s.`,
    backToSkills: "← Pick a different skill",
    sent: "Sent for grading…",
  },
  es: {
    title: "Práctica",
    pick: "Elige una habilidad para grabar",
    steps: "Pasos",
    record: "Graba un clip",
    choose: "Elige el archivo de video",
    rules: `${MIN_DURATION}-${MAX_DURATION}s · debe ser un archivo de video`,
    uploading: "Subiendo…",
    tooLong: (d) =>
      `El clip dura ${d.toFixed(1)}s. Graba menos de ${MAX_DURATION}s.`,
    tooShort: (d) =>
      `El clip dura ${d.toFixed(1)}s. Graba al menos ${MIN_DURATION}s.`,
    backToSkills: "← Elegir otra habilidad",
    sent: "Enviado a evaluación…",
  },
  tl: {
    title: "Pagsasanay",
    pick: "Pumili ng kasanayan para i-video",
    steps: "Mga hakbang",
    record: "Mag-record ng clip",
    choose: "Pumili ng video file",
    rules: `${MIN_DURATION}-${MAX_DURATION}s · dapat tunay na video file`,
    uploading: "Ina-upload…",
    tooLong: (d) =>
      `Ang clip ay ${d.toFixed(1)}s. Pakimasusing mas maigsi sa ${MAX_DURATION}s.`,
    tooShort: (d) =>
      `Ang clip ay ${d.toFixed(1)}s. Dapat ay hindi bababa sa ${MIN_DURATION}s.`,
    backToSkills: "← Pumili ng ibang kasanayan",
    sent: "Pinadala para sa pagmamarka…",
  },
};

function pickTranslation(skill, language) {
  const base = { title: skill.title, steps: skill.steps || [] };
  if (!language || language === "en") return base;
  const t = (skill.translations || {})[language];
  if (!t) return base;
  const localizedSteps = (t.steps || []).map((s, i) => ({
    ...skill.steps[i],
    title: s.title,
    instruction: s.instruction,
  }));
  return {
    title: t.title || skill.title,
    steps: localizedSteps.length ? localizedSteps : skill.steps || [],
  };
}

export default function PracticePage() {
  const { caregiver, code } = useCaregiver();
  const navigate = useNavigate();
  const t = T[caregiver.language] || T.en;
  const [skills, setSkills] = useState(null);
  const [statusByCaregiver, setStatusByCaregiver] = useState({});
  const [selected, setSelected] = useState(null);
  const [state, setState] = useState({ status: "idle" });

  useEffect(() => {
    // Fetch skill full docs (not just the list) so we have translations/steps.
    // Also pull `/lessons/caregiver/{id}` for the per-skill status chip —
    // same source agency uses, so no duplicate logic (Stage 2 — Item G).
    Promise.all([
      api.get("/lessons/skills"),
      api.get(`/lessons/caregiver/${caregiver.id}`),
    ])
      .then(([s, cg]) => {
        setSkills(s.data.skills);
        const byId = {};
        for (const row of [...(cg.data.cleared || []), ...(cg.data.remaining || [])]) {
          byId[row.id] = row.status;
        }
        setStatusByCaregiver(byId);
      })
      .catch(() => setSkills([]));
  }, [caregiver.id]);

  // We only have titles from /lessons/skills. For step + translation data,
  // fetch per-skill via a sibling endpoint we added for grading: use the
  // competency per-caregiver response (has skill titles but not steps).
  // Pragmatic fallback: enrich only when the caregiver taps a skill, by
  // calling a dedicated endpoint. We add one lightweight path below using
  // /ops data; otherwise we show a step list placeholder.
  const [enriched, setEnriched] = useState(null);
  useEffect(() => {
    if (!selected) {
      setEnriched(null);
      return;
    }
    setEnriched({ status: "loading" });
    api
      .get(`/grading/skill/${selected.id}`)
      .then((r) => setEnriched({ status: "ok", skill: r.data.skill }))
      .catch(() =>
        setEnriched({ status: "ok", skill: { ...selected, steps: [] } }),
      );
  }, [selected]);

  if (!selected) {
    return (
      <div className="px-5 py-6 space-y-4" data-testid="practice-page">
        <h2 className="text-2xl font-semibold">{t.title}</h2>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          {t.pick}
        </p>
        {skills == null ? (
          <p style={{ color: "var(--fs-muted)" }} className="font-ui text-sm">
            …
          </p>
        ) : (
          <ul
            className="fs-card fs-divider"
            data-testid="practice-skill-list"
          >
            {skills.map((s) => {
              const status = statusByCaregiver[s.id];
              const chipLabel = CHIP_LABELS[caregiver.language]?.[status] || CHIP_LABELS.en[status];
              return (
                <li key={s.id}>
                  <button
                    type="button"
                    onClick={() => setSelected(s)}
                    data-testid={`practice-pick-${s.id}`}
                    className="w-full tap text-left px-4 py-4 flex items-center gap-3"
                  >
                    <span className="flex-1 font-semibold leading-snug min-w-0">
                      {s.title}
                    </span>
                    <span
                      className="font-ui text-xs whitespace-nowrap"
                      style={{ color: "var(--fs-muted)" }}
                    >
                      {s.step_count} steps
                    </span>
                    {chipLabel ? (
                      <span
                        className={`fs-chip whitespace-nowrap ${chipClass(status)}`}
                        data-testid={`practice-chip-${s.id}`}
                      >
                        {chipLabel}
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    );
  }

  const localised =
    enriched?.status === "ok"
      ? pickTranslation(enriched.skill, caregiver.language)
      : null;

  async function onFile(e) {
    const file = e.target.files?.[0];
    if (!file) return;
    const url = URL.createObjectURL(file);
    const video = document.createElement("video");
    video.preload = "metadata";
    video.src = url;
    const duration = await new Promise((resolve) => {
      video.onloadedmetadata = () => resolve(video.duration);
      video.onerror = () => resolve(NaN);
    });
    URL.revokeObjectURL(url);
    if (!Number.isFinite(duration)) {
      setState({ status: "error", error: t.tooShort(0) });
      return;
    }
    if (duration > MAX_DURATION) {
      setState({ status: "error", error: t.tooLong(duration) });
      return;
    }
    if (duration < MIN_DURATION) {
      setState({ status: "error", error: t.tooShort(duration) });
      return;
    }
    const fd = new FormData();
    fd.append("file", file);
    fd.append("skill_id", selected.id);
    fd.append("caregiver_id", caregiver.id);
    setState({ status: "uploading", progress: 0 });
    try {
      const r = await api.post("/grading/clips", fd, {
        headers: { "Content-Type": "multipart/form-data" },
        onUploadProgress: (ev) =>
          setState({
            status: "uploading",
            progress: Math.round((ev.loaded / (ev.total || 1)) * 100),
          }),
      });
      navigate(`/c/${code}/practice/${r.data.attempt_id}`);
    } catch (err) {
      setState({
        status: "error",
        error: err?.response?.data?.detail || err.message,
      });
    }
  }

  return (
    <div className="px-5 py-6 space-y-5" data-testid="practice-detail">
      <button
        type="button"
        onClick={() => {
          setSelected(null);
          setState({ status: "idle" });
        }}
        className="font-ui text-sm underline"
        data-testid="practice-back"
      >
        {t.backToSkills}
      </button>
      <header>
        <h2 className="text-2xl font-semibold">
          {localised?.title || selected.title}
        </h2>
      </header>
      <section>
        <h3
          className="text-xs uppercase tracking-wide font-ui mb-2"
          style={{ color: "var(--fs-muted)" }}
        >
          {t.steps}
        </h3>
        {!localised ? (
          <p className="font-ui text-sm" style={{ color: "var(--fs-muted)" }}>
            …
          </p>
        ) : (
          <ol
            className="fs-card fs-divider"
            data-testid="practice-steps"
          >
            {localised.steps.map((s, i) => (
              <li
                key={i}
                className="px-4 py-3"
                data-testid={`practice-step-${i + 1}`}
              >
                <div className="font-semibold">
                  {i + 1}. {s.title}
                </div>
                {s.instruction && s.instruction !== s.title ? (
                  <div
                    className="font-ui text-xs mt-1"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {s.instruction}
                  </div>
                ) : null}
              </li>
            ))}
          </ol>
        )}
      </section>
      <section>
        <h3
          className="text-xs uppercase tracking-wide font-ui mb-2"
          style={{ color: "var(--fs-muted)" }}
        >
          {t.record}
        </h3>
        <label className="fs-card p-4 flex flex-col gap-2 cursor-pointer tap"
          data-testid="practice-record-wrap">
          <span className="font-semibold">{t.choose}</span>
          <span
            className="font-ui text-xs"
            style={{ color: "var(--fs-muted)" }}
          >
            {t.rules}
          </span>
          <input
            type="file"
            accept="video/*"
            capture="environment"
            className="hidden"
            onChange={onFile}
            disabled={state.status === "uploading"}
            data-testid="practice-file-input"
          />
        </label>
        {state.status === "uploading" ? (
          <p
            className="font-ui text-sm mt-3"
            data-testid="practice-upload-progress"
          >
            {t.uploading} {state.progress ?? 0}%
          </p>
        ) : null}
        {state.status === "error" ? (
          <p
            className="font-ui text-sm mt-3"
            style={{ color: "var(--fs-fail)" }}
            data-testid="practice-error"
          >
            {state.error}
          </p>
        ) : null}
      </section>
    </div>
  );
}
