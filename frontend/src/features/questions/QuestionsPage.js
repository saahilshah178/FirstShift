import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api";
import { useCaps } from "@/hooks/useRole";

export default function QuestionsPage() {
  const [inbox, setInbox] = useState({ waiting: [], answered: [] });
  const [err, setErr] = useState(null);
  const [activeId, setActiveId] = useState(null);
  const detailRef = useRef(null);

  const load = useCallback(async (signal) => {
    try {
      const r = await api.get("/questions/inbox", { signal });
      setInbox({
        waiting: r.data.waiting || [],
        answered: r.data.answered || [],
      });
    } catch (e) {
      if (
        e?.name === "CanceledError" ||
        e?.name === "AbortError" ||
        e?.code === "ERR_CANCELED"
      ) {
        return;
      }
      setErr(e?.message || "failed");
    }
  }, []);

  useEffect(() => {
    // Stage 4-G: abort guard silences the StrictMode double-mount dev
    // dup. Production hits the endpoint once.
    const ac = new AbortController();
    load(ac.signal);
    return () => ac.abort();
  }, [load]);
  useEffect(() => {
    // Stage 4-G: polling trimmed to 10s. The Care Manager inbox doesn't
    // need second-level freshness — new questions still appear within
    // one polling window and manual nav still forces a fresh fetch.
    const t = setInterval(() => load(), 10000);
    return () => clearInterval(t);
  }, [load]);

  const active = [...inbox.waiting, ...inbox.answered].find((q) => q.id === activeId) || null;

  const onPick = useCallback((id) => {
    setActiveId(id);
    // Scroll the detail into view on the first tap at the ~480px
    // column — the panel is stacked BELOW the list so taps on rows
    // further down the inbox would otherwise feel like no-ops.
    requestAnimationFrame(() => {
      if (detailRef.current) {
        detailRef.current.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    });
  }, []);

  return (
    <section data-testid="questions-page" className="space-y-5">
      <header>
        <h1 className="text-2xl font-semibold">Questions</h1>
        <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          Caregiver questions. Waiting ones come first.
        </p>
      </header>

      {err ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }}>
          {err}
        </p>
      ) : null}

      {/* Stage 4-A: layout always stacks at the agency column
          (~480px). The answer panel renders BELOW the list, never
          beside it — single column of thought at this width. */}
      <div className="space-y-5">
        <aside data-testid="questions-list" className="space-y-4">
          <Column
            title={`Waiting (${inbox.waiting.length})`}
            rows={inbox.waiting}
            activeId={activeId}
            onPick={onPick}
            tone="warn"
          />
          <Column
            title={`Answered (${inbox.answered.length})`}
            rows={inbox.answered}
            activeId={activeId}
            onPick={onPick}
            tone="pass"
          />
          {inbox.waiting.length + inbox.answered.length === 0 ? (
            <p
              className="fs-card px-4 py-3 text-sm"
              style={{ color: "var(--fs-muted)" }}
              data-testid="questions-empty"
            >
              Nothing in the inbox yet.
            </p>
          ) : null}
        </aside>
        <main data-testid="questions-detail" ref={detailRef}>
          {active ? (
            <Detail
              question={active}
              onDone={() => {
                setActiveId(null);
                load();
              }}
            />
          ) : (
            <p
              className="fs-card px-4 py-6 text-sm"
              style={{ color: "var(--fs-muted)" }}
            >
              Tap a question above to open it.
            </p>
          )}
        </main>
      </div>
    </section>
  );
}

function Column({ title, rows, activeId, onPick, tone }) {
  if (!rows || rows.length === 0) return null;
  const color = tone === "warn" ? "var(--fs-warn)" : "var(--fs-pass)";
  return (
    <section>
      <h3
        className="text-xs uppercase tracking-wide font-ui mb-2"
        style={{ color }}
      >
        {title}
      </h3>
      <ul className="fs-card fs-divider">
        {rows.map((q) => (
          <li key={q.id}>
            {/* Stage 4-C: full-row click target. The <button> is
                full-width + text-left so the entire row is tappable,
                not just the title. Keyboard navigable because it's a
                button, not a <li onClick>. */}
            <button
              type="button"
              onClick={() => onPick(q.id)}
              data-testid={`questions-row-${q.id}`}
              aria-pressed={activeId === q.id}
              className="w-full text-left px-4 py-3 tap"
              style={{
                background:
                  activeId === q.id ? "var(--fs-accent)" : "transparent",
              }}
            >
              <p className="text-sm font-semibold break-words">{q.text}</p>
              <p
                className="text-xs font-ui mt-0.5"
                style={{ color: "var(--fs-muted)" }}
              >
                {q.caregiver?.name || "unknown"} · {q.language}
              </p>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}

function sourceLabel(src) {
  if (src === "owner") return "Care Manager";
  if (src === "gemini") return "AI";
  return src || "unknown";
}

function Detail({ question, onDone }) {
  const { can } = useCaps();
  const canAnswer = can.answerQuestions;
  const [answer, setAnswer] = useState("");
  const [recState, setRecState] = useState("idle"); // idle | recording | transcribing | ready
  const [recErr, setRecErr] = useState(null);
  const [saving, setSaving] = useState(false);
  const [saveErr, setSaveErr] = useState(null);
  const mediaRecorderRef = useRef(null);
  const chunksRef = useRef([]);

  useEffect(() => {
    setAnswer("");
    setRecErr(null);
    setSaveErr(null);
    setRecState("idle");
  }, [question.id]);

  const startRecording = async () => {
    setRecErr(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream, { mimeType: "audio/webm" });
      chunksRef.current = [];
      mr.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setRecState("transcribing");
        try {
          const blob = new Blob(chunksRef.current, { type: "audio/webm" });
          const form = new FormData();
          form.append("file", blob, "voice.webm");
          const r = await api.post("/questions/transcribe", form, {
            headers: { "Content-Type": "multipart/form-data" },
          });
          setAnswer((prev) => (prev ? `${prev} ${r.data.transcript}`.trim() : r.data.transcript || ""));
          setRecState("ready");
        } catch (e) {
          setRecErr(e?.message || "transcription failed");
          setRecState("idle");
        }
      };
      mediaRecorderRef.current = mr;
      mr.start();
      setRecState("recording");
    } catch (e) {
      setRecErr(e?.message || "mic unavailable");
      setRecState("idle");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
      mediaRecorderRef.current.stop();
    }
  };

  const save = async () => {
    const t = answer.trim();
    if (!t) {
      setSaveErr("Answer required");
      return;
    }
    setSaving(true);
    setSaveErr(null);
    try {
      await api.post(`/questions/${question.id}/answer`, { text: t });
      onDone();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setSaveErr(typeof detail === "string" ? detail : e?.message || "save failed");
    } finally {
      setSaving(false);
    }
  };

  return (
    <article
      className="fs-card p-5 space-y-4 min-w-0 break-words"
      data-testid={`question-detail-${question.id}`}
    >
      <header>
        <p className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
          {question.caregiver?.name} · {question.language} ·{" "}
          {new Date(question.created_at).toLocaleString()}
        </p>
        <p className="text-base mt-1 font-semibold break-words" data-testid="question-detail-text">
          {question.text}
        </p>
      </header>

      {question.status === "answered" ? (
        <section
          className="rounded-lg p-3"
          style={{ background: "var(--fs-accent)" }}
          data-testid="question-detail-answered"
        >
          <p
            className="text-xs uppercase font-ui tracking-wide mb-1"
            style={{ color: "var(--fs-pass)" }}
          >
            Answered by {sourceLabel(question.source)}
          </p>
          <p className="text-sm whitespace-pre-wrap break-words">{question.answer}</p>
        </section>
      ) : !canAnswer ? (
        // Stage 4-D: Scheduler/Trainer on an unanswered question see
        // the question text itself (already rendered above). No "Switch
        // to Care Manager" nag — the role switch is in the top bar.
        null
      ) : (
        <>
          <section className="space-y-2">
            <label className="block">
              <span
                className="text-xs font-ui mb-1 block"
                style={{ color: "var(--fs-muted)" }}
              >
                Answer (editable — type or record a voice note)
              </span>
              <textarea
                value={answer}
                onChange={(e) => setAnswer(e.target.value)}
                rows={4}
                data-testid="answer-textarea"
                className="w-full rounded-lg p-3 font-ui text-sm"
                style={{
                  background: "var(--fs-surface)",
                  color: "var(--fs-fg)",
                  border: "1px solid var(--fs-border)",
                }}
              />
            </label>
            <div className="flex items-center gap-3 flex-wrap">
              {recState === "recording" ? (
                <button
                  type="button"
                  onClick={stopRecording}
                  data-testid="record-stop-btn"
                  className="tap px-3 rounded-full text-sm font-ui"
                  style={{
                    background: "var(--fs-fail)",
                    color: "var(--fs-primary-fg)",
                  }}
                >
                  ⏹ Stop
                </button>
              ) : (
                <button
                  type="button"
                  onClick={startRecording}
                  disabled={recState === "transcribing"}
                  data-testid="record-start-btn"
                  className="tap px-3 rounded-full text-sm font-ui border"
                  style={{ borderColor: "var(--fs-border)" }}
                >
                  {recState === "transcribing" ? "Transcribing…" : "🎙 Record"}
                </button>
              )}
              {recErr ? (
                <span
                  className="text-xs"
                  style={{ color: "var(--fs-fail)" }}
                  data-testid="record-err"
                >
                  {recErr}
                </span>
              ) : null}
            </div>
          </section>

          {saveErr ? (
            <p className="text-sm" style={{ color: "var(--fs-fail)" }} data-testid="answer-save-err">
              {saveErr}
            </p>
          ) : null}

          <button
            type="button"
            onClick={save}
            disabled={saving || !answer.trim()}
            data-testid="answer-save-btn"
            className="tap px-4 rounded-full text-sm font-ui"
            style={{
              background: "var(--fs-primary)",
              color: "var(--fs-primary-fg)",
              opacity: saving || !answer.trim() ? 0.5 : 1,
            }}
          >
            {saving ? "Sending…" : "Send answer"}
          </button>
        </>
      )}
    </article>
  );
}
