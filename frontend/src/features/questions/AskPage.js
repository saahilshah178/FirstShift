import React, { useState } from "react";
import { useCaregiver } from "@/shell/CaregiverLayout";

export default function AskPage() {
  const { caregiver } = useCaregiver();
  const [text, setText] = useState("");
  const [submitted, setSubmitted] = useState(false);

  return (
    <div className="px-5 py-6" data-testid="caregiver-ask-page">
      <h2 className="text-xl font-semibold">Ask a question</h2>
      <p className="mt-1 text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
        Your supervisor will respond here. (Phase 1 — not wired yet.)
      </p>
      <form
        className="mt-4 space-y-3"
        onSubmit={(e) => {
          e.preventDefault();
          setSubmitted(true);
          setText("");
        }}
      >
        <textarea
          data-testid="ask-textarea"
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
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
          disabled={!text.trim()}
          data-testid="ask-submit"
          className="tap font-ui text-sm px-4 rounded-full disabled:opacity-50"
          style={{
            background: "var(--fs-primary)",
            color: "var(--fs-primary-fg)",
          }}
        >
          Send
        </button>
      </form>
      {submitted ? (
        <p
          className="mt-3 text-sm"
          style={{ color: "var(--fs-primary)" }}
          data-testid="ask-sent"
        >
          Thanks — we got it. (placeholder)
        </p>
      ) : null}
    </div>
  );
}
