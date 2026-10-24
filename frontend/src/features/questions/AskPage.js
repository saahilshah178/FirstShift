import React, { useCallback, useEffect, useState } from "react";
import { useCaregiver } from "@/shell/CaregiverLayout";
import { api } from "@/api";

export default function AskPage() {
  const { caregiver } = useCaregiver();
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [history, setHistory] = useState([]);
  const [err, setErr] = useState(null);

  const load = useCallback(async () => {
    try {
      const r = await api.get("/questions/list");
      const mine = (r.data.questions || []).filter(
        (q) => q.caregiver_id === caregiver.id,
      );
      mine.sort((a, b) => (b.created_at || "").localeCompare(a.created_at || ""));
      setHistory(mine);
    } catch (e) {
      setErr(e?.message || "failed");
    }
  }, [caregiver.id]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    const t = setInterval(() => load(), 3000);
    return () => clearInterval(t);
  }, [load]);

  const send = async (e) => {
    e.preventDefault();
    const q = text.trim();
    if (!q) return;
    setSending(true);
    setErr(null);
    try {
      await api.post("/questions/ask", {
        caregiver_id: caregiver.id,
        text: q,
      });
      setText("");
      await load();
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : e2?.message || "failed");
    } finally {
      setSending(false);
    }
  };

  return (
    <div className="px-5 py-6 space-y-5" data-testid="caregiver-ask-page">
      <header>
        <h2 className="text-xl font-semibold">Ask a question</h2>
        <p className="mt-1 text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
          We'll answer from the agency's playbook. Anything we can't answer
          goes to your care manager.
        </p>
      </header>

      <form onSubmit={send} className="space-y-3">
        <textarea
          data-testid="ask-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={4}
          placeholder={`Hi, I'm ${caregiver.name.split(" ")[0]}. I'd like to ask…`}
          className="w-full rounded-lg p-3 font-ui text-sm"
          style={{
            background: "var(--fs-surface)",
            color: "var(--fs-fg)",
            border: "1px solid var(--fs-border)",
          }}
        />
        <button
          type="submit"
          disabled={!text.trim() || sending}
          data-testid="ask-submit"
          className="tap font-ui text-sm px-4 rounded-full disabled:opacity-50"
          style={{
            background: "var(--fs-primary)",
            color: "var(--fs-primary-fg)",
          }}
        >
          {sending ? "Sending…" : "Send"}
        </button>
      </form>

      {err ? (
        <p className="text-sm" style={{ color: "var(--fs-fail)" }} data-testid="ask-error">
          {err}
        </p>
      ) : null}

      <section data-testid="ask-history" className="space-y-3">
        <h3
          className="text-xs uppercase tracking-wide font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          Your questions
        </h3>
        {history.length === 0 ? (
          <p className="text-sm" style={{ color: "var(--fs-muted)" }}>
            No questions yet.
          </p>
        ) : (
          <ul className="fs-card fs-divider">
            {history.map((q, i) => (
              <li key={i} className="px-4 py-3 space-y-1" data-testid={`ask-row-${i}`}>
                <p className="text-sm font-semibold">{q.text}</p>
                {q.status === "answered" ? (
                  <p
                    className="text-sm font-ui"
                    style={{ color: "var(--fs-fg)" }}
                    data-testid={`ask-answer-${i}`}
                  >
                    {q.answer}
                  </p>
                ) : (
                  <p
                    className="text-xs font-ui italic"
                    style={{ color: "var(--fs-warn)" }}
                    data-testid={`ask-waiting-${i}`}
                  >
                    Waiting for your care manager…
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
