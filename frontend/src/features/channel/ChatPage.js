import React, { useCallback, useEffect, useRef, useState } from "react";
import { useCaregiver } from "@/shell/CaregiverLayout";
import { api, absoluteUrl } from "@/api";

export default function ChatPage() {
  const { caregiver, agency } = useCaregiver();
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState(null);
  const [convState, setConvState] = useState(null);
  const [uploading, setUploading] = useState(false);
  const videoInputRef = useRef(null);
  const scrollRef = useRef(null);

  const load = useCallback(async () => {
    try {
      const [m, c] = await Promise.all([
        api.get(`/channel/messages/${caregiver.id}`),
        api.get(`/channel/conversation/${caregiver.id}`),
      ]);
      setMessages(m.data.messages || []);
      setConvState(c.data || null);
    } catch (e) {
      setErr(e?.message || "failed");
    }
  }, [caregiver.id]);

  useEffect(() => {
    load();
  }, [load]);

  // Poll every 2s. Keep polling always so the signoff "You're cleared"
  // message surfaces without the caregiver sending anything.
  useEffect(() => {
    const t = setInterval(() => load(), 2000);
    return () => clearInterval(t);
  }, [load]);

  // Auto-scroll on new messages.
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages.length]);

  const sendText = async (payload) => {
    const content = (payload ?? text).trim();
    if (!content) return;
    setSending(true);
    setErr(null);
    try {
      await api.post("/channel/inbound", {
        caregiver_id: caregiver.id,
        text: content,
      });
      setText("");
      await load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : e?.message || "failed");
    } finally {
      setSending(false);
    }
  };

  const handleKey = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendText();
    }
  };

  const onPickVideo = async (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    setUploading(true);
    setErr(null);
    try {
      const form = new FormData();
      form.append("caregiver_id", caregiver.id);
      form.append("file", f);
      await api.post("/channel/inbound-video", form, {
        headers: { "Content-Type": "multipart/form-data" },
      });
      await load();
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : e2?.message || "upload failed");
    } finally {
      setUploading(false);
      if (videoInputRef.current) videoInputRef.current.value = "";
    }
  };

  const quickReplies = (() => {
    if (convState?.state === "quiz") return ["1", "2", "3"];
    if (convState?.state === "in_lesson") return ["Next"];
    if (convState?.state === "idle") return ["1", "2", "3"];
    return [];
  })();

  return (
    <div className="min-h-full flex flex-col" data-testid="caregiver-chat-page">
      {/* Thread */}
      <section
        ref={scrollRef}
        data-testid="chat-thread"
        className="flex-1 px-4 py-4 space-y-2 overflow-y-auto"
        style={{ minHeight: "60vh", maxHeight: "68vh" }}
      >
        {messages.length === 0 ? (
          <div
            className="fs-card p-4 text-center"
            data-testid="chat-empty"
            style={{ color: "var(--fs-muted)" }}
          >
            <p className="text-xs font-ui mb-1">
              {agency?.name} · {new Date().toLocaleDateString()}
            </p>
            <p className="text-sm">
              Say hi to get started — try typing <strong>menu</strong>.
            </p>
          </div>
        ) : null}
        {messages.map((m) => (
          <Bubble key={m.id} m={m} />
        ))}
        {convState?.state === "awaiting_result" ? (
          <div
            data-testid="chat-grading-indicator"
            className="text-xs font-ui italic"
            style={{ color: "var(--fs-muted)" }}
          >
            Checking your video…
          </div>
        ) : null}
      </section>

      {/* Error */}
      {err ? (
        <p
          className="px-4 text-sm"
          style={{ color: "var(--fs-fail)" }}
          data-testid="chat-error"
        >
          {err}
        </p>
      ) : null}

      {/* Composer */}
      <section
        className="px-3 py-3 border-t"
        style={{
          borderColor: "var(--fs-border)",
          background: "var(--fs-surface)",
        }}
      >
        {quickReplies.length > 0 ? (
          <div
            className="flex gap-2 mb-2"
            data-testid="chat-quick-replies"
          >
            {quickReplies.map((q) => (
              <button
                key={q}
                type="button"
                onClick={() => sendText(q)}
                disabled={sending}
                data-testid={`chat-quick-${q.toLowerCase()}`}
                className="tap px-3 rounded-full text-sm font-ui border"
                style={{
                  borderColor: "var(--fs-border)",
                  color: "var(--fs-fg)",
                }}
              >
                {q}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex items-end gap-2">
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKey}
            disabled={sending || uploading}
            rows={1}
            placeholder="Type a message…"
            data-testid="chat-input"
            className="flex-1 min-h-11 rounded-xl px-3 py-2 font-ui text-sm resize-none"
            style={{
              background: "var(--fs-surface)",
              color: "var(--fs-fg)",
              border: "1px solid var(--fs-border)",
            }}
          />
          <button
            type="button"
            onClick={() => videoInputRef.current && videoInputRef.current.click()}
            disabled={uploading || convState?.state !== "awaiting_video"}
            data-testid="chat-video-btn"
            className="tap px-3 rounded-full text-xs font-ui border"
            style={{
              borderColor: "var(--fs-border)",
              color: convState?.state === "awaiting_video" ? "var(--fs-primary)" : "var(--fs-muted)",
              opacity: convState?.state === "awaiting_video" ? 1 : 0.55,
            }}
          >
            🎥
          </button>
          <input
            ref={videoInputRef}
            type="file"
            accept="video/mp4,video/webm,video/quicktime"
            capture="environment"
            onChange={onPickVideo}
            data-testid="chat-video-input"
            className="hidden"
          />
          <button
            type="button"
            onClick={() => sendText()}
            disabled={sending || !text.trim()}
            data-testid="chat-send-btn"
            className="tap px-4 rounded-full text-sm font-ui"
            style={{
              background: "var(--fs-primary)",
              color: "var(--fs-primary-fg)",
              opacity: sending || !text.trim() ? 0.5 : 1,
            }}
          >
            {sending ? "…" : "Send"}
          </button>
        </div>
        {uploading ? (
          <p
            className="text-xs font-ui mt-2"
            style={{ color: "var(--fs-muted)" }}
            data-testid="chat-uploading"
          >
            Uploading video…
          </p>
        ) : null}
      </section>
    </div>
  );
}

function Bubble({ m }) {
  const outbound = m.direction === "out";
  return (
    <div
      className={`flex ${outbound ? "justify-start" : "justify-end"}`}
      data-testid={`chat-msg-${m.id}`}
    >
      <div
        className="rounded-2xl px-4 py-2 max-w-[82%]"
        style={{
          background: outbound ? "var(--fs-accent)" : "var(--fs-primary)",
          color: outbound ? "var(--fs-fg)" : "var(--fs-primary-fg)",
          whiteSpace: "pre-wrap",
          wordBreak: "break-word",
        }}
      >
        {m.media_id && !outbound ? (
          <video
            src={absoluteUrl(`/api/media/${m.media_id}`)}
            controls
            data-testid={`chat-msg-video-${m.id}`}
            className="rounded-lg mb-1 w-full"
            style={{ maxHeight: 160 }}
          />
        ) : null}
        {m.media_id && outbound ? (
          <img
            src={absoluteUrl(`/api/media/${m.media_id}`)}
            alt=""
            data-testid={`chat-msg-image-${m.id}`}
            className="rounded-lg mb-1 w-full"
            style={{ maxHeight: 180, objectFit: "cover" }}
          />
        ) : null}
        <p className="text-sm leading-snug">{m.text}</p>
        <p
          className="text-[10px] font-ui mt-1 opacity-70"
          data-testid={`chat-msg-time-${m.id}`}
        >
          {new Date(m.created_at).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
          })}
        </p>
      </div>
    </div>
  );
}
