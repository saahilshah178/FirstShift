import React from "react";
import { useCaregiver } from "@/shell/CaregiverLayout";

export default function ChatPage() {
  const { caregiver, agency } = useCaregiver();
  return (
    <div
      className="min-h-full px-5 py-6 flex flex-col"
      data-testid="caregiver-chat-page"
    >
      <section className="flex-1">
        <div
          className="fs-card p-5"
          style={{ background: "var(--fs-accent)", borderColor: "transparent" }}
        >
          <p className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
            {agency?.name} · {new Date().toLocaleDateString()}
          </p>
          <h2 className="mt-1 text-xl font-semibold">
            Welcome, {caregiver.name.split(" ")[0]}.
          </h2>
          <p className="mt-2 font-ui text-sm" style={{ color: "var(--fs-fg)" }}>
            Messages from your supervisor will appear here. Tap{" "}
            <span className="font-semibold">Lessons</span> to see what's queued
            for you, or <span className="font-semibold">Ask</span> if you have
            a question.
          </p>
        </div>
      </section>
      <section
        className="mt-6"
        aria-label="Message composer (placeholder)"
      >
        <div
          className="flex items-center gap-2 rounded-full px-4 py-2"
          style={{ background: "var(--fs-surface)" }}
          data-testid="caregiver-composer"
        >
          <span style={{ color: "var(--fs-muted)" }} className="font-ui text-sm">
            Message your supervisor…
          </span>
        </div>
      </section>
    </div>
  );
}
