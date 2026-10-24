import React, { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, absoluteUrl } from "@/api";

const ROLE_KEY = "firstshift.agency_role";

export default function SkillDetailPage() {
  const { skillId } = useParams();
  const nav = useNavigate();
  const role = localStorage.getItem(ROLE_KEY) || "Care Manager";
  const allowed = role === "Care Manager";
  const [skill, setSkill] = useState(null);
  const [err, setErr] = useState(null);
  const [lang, setLang] = useState("en");
  const [retrying, setRetrying] = useState(false);

  const load = useMemo(
    () => async () => {
      try {
        const r = await api.get(`/lessons/skills/${skillId}`);
        setSkill(r.data);
      } catch (e) {
        const detail = e?.response?.data?.detail;
        setErr(typeof detail === "string" ? detail : e?.message || "failed");
      }
    },
    [skillId],
  );
  useEffect(() => {
    load();
  }, [load]);

  if (!allowed) {
    return (
      <section className="space-y-3" data-testid="skill-detail-gate">
        <h1 className="text-2xl font-semibold">Skill</h1>
        <p
          className="text-sm font-ui fs-card px-4 py-3"
          style={{ color: "var(--fs-muted)" }}
        >
          Switch to Care Manager to record skills.
        </p>
      </section>
    );
  }

  if (err && !skill) {
    return (
      <section className="space-y-3" data-testid="skill-detail-error">
        <p style={{ color: "var(--fs-fail)" }}>{err}</p>
        <Link to="/skills" className="text-sm font-ui">Back</Link>
      </section>
    );
  }
  if (!skill) return <p data-testid="skill-detail-loading" style={{ color: "var(--fs-muted)" }}>Loading…</p>;

  const openEdit = async () => {
    try {
      const r = await api.post(`/lessons/skills/${skillId}/edit`);
      nav(`/skills/drafts/${r.data.job_id}`);
    } catch (e) {
      setErr(e?.message || "edit failed");
    }
  };

  const retryTranslations = async () => {
    setRetrying(true);
    try {
      await api.post(`/lessons/skills/${skillId}/translations/retry`);
      await load();
    } catch (e) {
      setErr(e?.message || "translate failed");
    } finally {
      setRetrying(false);
    }
  };

  return (
    <section className="space-y-5" data-testid="skill-detail">
      <header className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold" data-testid="skill-title">
            {skill.title}
          </h1>
          <p className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
            Version {skill.version}
            {skill.source_credit ? ` · ${skill.source_credit}` : ""}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={openEdit}
            data-testid="skill-edit-btn"
            className="tap px-3 text-sm font-ui rounded-full border"
            style={{ borderColor: "var(--fs-border)" }}
          >
            Edit skill
          </button>
          <Link to="/skills" className="text-sm font-ui" data-testid="skill-back">
            Back
          </Link>
        </div>
      </header>

      {/* Lang tabs */}
      <nav className="flex gap-2 border-b" style={{ borderColor: "var(--fs-border)" }} data-testid="skill-lang-tabs">
        {[{ k: "en", label: "English" }, { k: "es", label: "Español" }, { k: "tl", label: "Tagalog" }].map((t) => (
          <button
            key={t.k}
            type="button"
            onClick={() => setLang(t.k)}
            data-testid={`skill-tab-${t.k}`}
            className="tap px-3 text-sm font-ui"
            style={{
              borderBottom: lang === t.k ? "2px solid var(--fs-primary)" : "2px solid transparent",
              color: lang === t.k ? "var(--fs-primary)" : "var(--fs-muted)",
              fontWeight: lang === t.k ? 600 : 400,
            }}
          >
            {t.label}
          </button>
        ))}
      </nav>

      {lang === "en" ? (
        <EnglishView skill={skill} />
      ) : (
        <TranslationView
          skill={skill}
          lang={lang}
          onEdited={load}
          onReview={async () => {
            await api.post(`/lessons/skills/${skillId}/translations/${lang}/review`);
            load();
          }}
          onRetry={retryTranslations}
          retrying={retrying}
        />
      )}
    </section>
  );
}

function EnglishView({ skill }) {
  return (
    <div className="space-y-5" data-testid="skill-en-view">
      <section>
        <h2 className="text-xs uppercase tracking-wide font-ui mb-2" style={{ color: "var(--fs-muted)" }}>
          Steps ({skill.steps.length})
        </h2>
        <ol className="space-y-3">
          {skill.steps.map((s) => (
            <li key={s.n} className="fs-card p-3 flex gap-3" data-testid={`skill-en-step-${s.n}`}>
              {s.frame_id ? (
                <img
                  src={absoluteUrl(`/api/media/${s.frame_id}`)}
                  alt={`Step ${s.n}`}
                  data-testid={`skill-en-frame-${s.n}`}
                  className="w-28 h-20 object-cover rounded-md"
                />
              ) : (
                <div className="w-28 h-20 rounded-md" style={{ background: "var(--fs-accent)" }} />
              )}
              <div className="min-w-0">
                <p className="font-semibold">{s.n}. {s.title}</p>
                <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>{s.instruction}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wide font-ui mb-2" style={{ color: "var(--fs-muted)" }}>
          Checks ({skill.checks.length})
        </h2>
        <ul className="fs-card fs-divider" data-testid="skill-en-checks">
          {skill.checks.map((c) => (
            <li key={c.id} className="px-3 py-2 flex items-center justify-between" data-testid={`skill-en-check-${c.id}`}>
              <span className="text-sm">{c.description}</span>
              {c.safety_critical ? (
                <span
                  className="fs-chip"
                  style={{ color: "var(--fs-fail)", borderColor: "var(--fs-fail)" }}
                  data-testid={`skill-en-check-safety-${c.id}`}
                >
                  safety-critical
                </span>
              ) : null}
            </li>
          ))}
        </ul>
      </section>

      <section>
        <h2 className="text-xs uppercase tracking-wide font-ui mb-2" style={{ color: "var(--fs-muted)" }}>
          Quiz ({skill.quiz.length})
        </h2>
        <ul className="space-y-3" data-testid="skill-en-quiz">
          {skill.quiz.map((q) => (
            <li key={q.id} className="fs-card p-3" data-testid={`skill-en-quiz-${q.id}`}>
              <p className="font-semibold mb-1">{q.prompt}</p>
              <ol className="text-sm space-y-1">
                {q.choices.map((o, i) => (
                  <li
                    key={i}
                    data-testid={`skill-en-quiz-${q.id}-opt-${i}`}
                    style={{
                      color: q.answer_index === i ? "var(--fs-pass)" : "var(--fs-fg)",
                      fontWeight: q.answer_index === i ? 600 : 400,
                    }}
                  >
                    {String.fromCharCode(65 + i)}. {o}{q.answer_index === i ? " ✓" : ""}
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function TranslationView({ skill, lang, onEdited, onReview, onRetry, retrying }) {
  const t = skill.translations[lang];
  const status = t?.status || "machine";
  const [editable, setEditable] = useState(false);
  const [title, setTitle] = useState(t?.title || "");
  const [steps, setSteps] = useState(t?.steps || []);
  const [checks, setChecks] = useState(t?.checks || []);
  const [quiz, setQuiz] = useState(t?.quiz || []);
  const [saveErr, setSaveErr] = useState(null);

  useEffect(() => {
    setTitle(t?.title || "");
    setSteps(t?.steps || []);
    setChecks(t?.checks || []);
    setQuiz(t?.quiz || []);
  }, [lang, t?.title, t?.steps, t?.checks, t?.quiz]);

  const save = async () => {
    setSaveErr(null);
    try {
      await api.put(`/lessons/skills/${skill.id}/translations/${lang}`, {
        title,
        steps,
        checks,
        quiz,
      });
      setEditable(false);
      onEdited();
    } catch (e) {
      setSaveErr(e?.message || "save failed");
    }
  };

  const showEnglishBeside = status !== "reviewed";

  return (
    <div className="space-y-5" data-testid={`skill-${lang}-view`}>
      <div className="flex items-center justify-between">
        <span
          className="fs-chip"
          data-testid={`skill-${lang}-status`}
          style={{
            color:
              status === "reviewed"
                ? "var(--fs-pass)"
                : status === "stale"
                  ? "var(--fs-warn)"
                  : "var(--fs-muted)",
            borderColor:
              status === "reviewed"
                ? "var(--fs-pass)"
                : status === "stale"
                  ? "var(--fs-warn)"
                  : "var(--fs-border)",
          }}
        >
          {status === "machine" ? "Machine-translated" : status === "reviewed" ? "Reviewed" : "Stale"}
        </span>
        <div className="flex items-center gap-2">
          {status === "stale" ? (
            <button
              type="button"
              onClick={onRetry}
              disabled={retrying}
              data-testid={`skill-${lang}-retry`}
              className="tap px-3 text-xs font-ui rounded-full border"
              style={{ borderColor: "var(--fs-border)" }}
            >
              {retrying ? "Retrying…" : "Retry translation"}
            </button>
          ) : null}
          {editable ? (
            <button
              type="button"
              onClick={save}
              data-testid={`skill-${lang}-save`}
              className="tap px-3 text-xs font-ui rounded-full"
              style={{ background: "var(--fs-primary)", color: "var(--fs-primary-fg)" }}
            >
              Save
            </button>
          ) : (
            <button
              type="button"
              onClick={() => setEditable(true)}
              data-testid={`skill-${lang}-edit`}
              className="tap px-3 text-xs font-ui rounded-full border"
              style={{ borderColor: "var(--fs-border)" }}
            >
              Edit
            </button>
          )}
          <button
            type="button"
            onClick={onReview}
            data-testid={`skill-${lang}-mark-reviewed`}
            className="tap px-3 text-xs font-ui rounded-full border"
            style={{ borderColor: "var(--fs-border)" }}
            disabled={status === "reviewed"}
          >
            {status === "reviewed" ? "Reviewed" : "Mark reviewed"}
          </button>
        </div>
      </div>

      {saveErr ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }}>{saveErr}</p>
      ) : null}

      {editable ? (
        <input
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          data-testid={`skill-${lang}-title-input`}
          className="block w-full text-lg font-semibold rounded-md px-3 py-2 border bg-transparent tap"
          style={{ borderColor: "var(--fs-border)" }}
        />
      ) : (
        <h2 className="text-lg font-semibold" data-testid={`skill-${lang}-title`}>{title}</h2>
      )}

      <section>
        <h3 className="text-xs uppercase tracking-wide font-ui mb-2" style={{ color: "var(--fs-muted)" }}>
          Steps ({steps.length})
        </h3>
        <ol className="space-y-3">
          {steps.map((s, i) => {
            const en = skill.steps.find((x) => x.n === s.n);
            return (
              <li key={s.n} className="fs-card p-3" data-testid={`skill-${lang}-step-${s.n}`}>
                {editable ? (
                  <>
                    <input
                      value={s.title || ""}
                      onChange={(e) => {
                        const next = [...steps];
                        next[i] = { ...s, title: e.target.value };
                        setSteps(next);
                      }}
                      data-testid={`skill-${lang}-step-title-${s.n}`}
                      className="block w-full font-semibold mb-1 rounded-md px-2 py-1 border bg-transparent"
                      style={{ borderColor: "var(--fs-border)" }}
                    />
                    <textarea
                      value={s.instruction || ""}
                      rows={2}
                      onChange={(e) => {
                        const next = [...steps];
                        next[i] = { ...s, instruction: e.target.value };
                        setSteps(next);
                      }}
                      data-testid={`skill-${lang}-step-instr-${s.n}`}
                      className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent"
                      style={{ borderColor: "var(--fs-border)" }}
                    />
                  </>
                ) : (
                  <>
                    <p className="font-semibold">{s.n}. {s.title}</p>
                    <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>{s.instruction}</p>
                  </>
                )}
              </li>
            );
          })}
        </ol>
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide font-ui mb-2" style={{ color: "var(--fs-muted)" }}>
          Checks ({checks.length})
        </h3>
        <ul className="fs-card fs-divider">
          {checks.map((c, i) => {
            const en = skill.checks.find((x) => x.id === c.id);
            const safetyCritical = en?.safety_critical;
            return (
              <li key={c.id} className="px-3 py-2 space-y-1" data-testid={`skill-${lang}-check-${c.id}`}>
                {editable ? (
                  <input
                    value={c.description || ""}
                    onChange={(e) => {
                      const next = [...checks];
                      next[i] = { ...c, description: e.target.value };
                      setChecks(next);
                    }}
                    data-testid={`skill-${lang}-check-desc-${c.id}`}
                    className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent"
                    style={{ borderColor: "var(--fs-border)" }}
                  />
                ) : (
                  <p className="text-sm">{c.description}</p>
                )}
                {safetyCritical && showEnglishBeside ? (
                  <p
                    className="text-xs font-ui"
                    style={{ color: "var(--fs-warn)" }}
                    data-testid={`skill-${lang}-check-en-${c.id}`}
                  >
                    ⚠ Safety-critical. English: <em>{en.description}</em>
                  </p>
                ) : safetyCritical ? (
                  <p className="text-xs font-ui" style={{ color: "var(--fs-fail)" }}>safety-critical</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      </section>

      <section>
        <h3 className="text-xs uppercase tracking-wide font-ui mb-2" style={{ color: "var(--fs-muted)" }}>
          Quiz ({quiz.length})
        </h3>
        <ul className="space-y-3">
          {quiz.map((q, i) => (
            <li key={q.id} className="fs-card p-3" data-testid={`skill-${lang}-quiz-${q.id}`}>
              {editable ? (
                <input
                  value={q.prompt || ""}
                  onChange={(e) => {
                    const next = [...quiz];
                    next[i] = { ...q, prompt: e.target.value };
                    setQuiz(next);
                  }}
                  data-testid={`skill-${lang}-quiz-prompt-${q.id}`}
                  className="block w-full font-semibold mb-1 rounded-md px-2 py-1 border bg-transparent"
                  style={{ borderColor: "var(--fs-border)" }}
                />
              ) : (
                <p className="font-semibold mb-1">{q.prompt}</p>
              )}
              <ol className="text-sm space-y-1">
                {(q.choices || []).map((o, j) => (
                  <li key={j} data-testid={`skill-${lang}-quiz-${q.id}-opt-${j}`}>
                    {editable ? (
                      <input
                        value={o}
                        onChange={(e) => {
                          const next = [...quiz];
                          const choices = [...q.choices];
                          choices[j] = e.target.value;
                          next[i] = { ...q, choices };
                          setQuiz(next);
                        }}
                        className="block w-full text-sm font-ui rounded-md px-2 py-1 border bg-transparent"
                        style={{ borderColor: "var(--fs-border)" }}
                      />
                    ) : (
                      <span>{String.fromCharCode(65 + j)}. {o}</span>
                    )}
                  </li>
                ))}
              </ol>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}
