import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useCaregiver } from "@/shell/CaregiverLayout";
import { api, absoluteUrl } from "@/api";

/* Localized "no quick reply yet, type a message" placeholder label and the
   generic "Send" button label used by the composer. Keep tiny — anything
   that comes from the FSM is already localized server-side. */
const COMPOSER_PLACEHOLDER = {
  en: "Type a message…",
  es: "Escribe un mensaje…",
  tl: "Mag-type ng mensahe…",
};

/* The LATEST outbound message is the single source of truth for the
   quick-reply bar (Stage 2 — Item A). If it has a `question_type`, the
   bar renders against it. If the latest outbound has no `question_type`,
   the bar is hidden (no stale carry-over from an earlier question). */
function latestQuestion(messages) {
  if (!Array.isArray(messages)) return null;
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const m = messages[i];
    if (!m || m.direction !== "out") continue;
    return m.question_type ? m : null;
  }
  return null;
}

export default function ChatPage() {
  const { caregiver, agency } = useCaregiver();
  const lang = caregiver.language || "en";
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [sending, setSending] = useState(false);
  const [err, setErr] = useState(null);
  const [convState, setConvState] = useState(null);
  const [uploading, setUploading] = useState(false);
  const videoInputRef = useRef(null);
  const inputRef = useRef(null);
  const scrollRef = useRef(null);
  const lastMessageIdRef = useRef(null);
  const userScrolledUpRef = useRef(false);

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

  // Track whether the user has scrolled up (preserve "don't jump down
  // while they're reading" behaviour). We only consider them "scrolled
  // up" when they are > 60 px from the bottom.
  const onThreadScroll = () => {
    const el = scrollRef.current;
    if (!el) return;
    const bottomGap = el.scrollHeight - el.scrollTop - el.clientHeight;
    userScrolledUpRef.current = bottomGap > 60;
  };

  // Auto-scroll on NEW last message. If the new message has <img>
  // children, wait for every image to resolve `onLoad`/`onError`
  // (whichever first) before scrolling, so the scroll lands on the
  // final rendered height (not the zero-height placeholder). Capped
  // at 1500 ms so a stuck image never freezes the UI.
  useEffect(() => {
    const last = messages[messages.length - 1];
    if (!last || !scrollRef.current) return;
    const id = last.id || last._id || last.at;
    if (lastMessageIdRef.current === id) return;
    lastMessageIdRef.current = id;
    if (userScrolledUpRef.current) return;

    const doScroll = () => {
      const el = scrollRef.current;
      if (!el) return;
      el.scrollTop = el.scrollHeight;
    };

    // Find <img> elements inside the latest bubble. We query by the
    // bubble's id so a mid-stream message doesn't delay the scroll.
    const bubble = scrollRef.current.querySelector(
      `[data-testid="chat-msg-${last.id}"]`,
    );
    const imgs = bubble ? Array.from(bubble.querySelectorAll("img")) : [];
    const pending = imgs.filter((img) => !img.complete);
    if (pending.length === 0) {
      doScroll();
      return;
    }
    let settled = false;
    const timer = setTimeout(() => {
      if (settled) return;
      settled = true;
      doScroll();
    }, 1500);
    Promise.all(
      pending.map(
        (img) =>
          new Promise((resolve) => {
            const done = () => resolve(null);
            img.addEventListener("load", done, { once: true });
            img.addEventListener("error", done, { once: true });
          }),
      ),
    ).then(() => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      doScroll();
    });
  }, [messages]);

  const refocusInput = () => {
    // Keep the composer focused so repeated quick-reply taps + manual
    // typing feel like one continuous conversation. `preventScroll`
    // stops the composer from stealing the scroll back from the thread
    // after the auto-scroll above. The `setTimeout(…, 0)` gives React
    // a tick to flush `setSending(false)` so the textarea is no longer
    // `disabled` when we call `.focus()` — focusing a disabled element
    // is a silent no-op in every modern browser.
    setTimeout(() => {
      if (inputRef.current && !inputRef.current.disabled) {
        inputRef.current.focus({ preventScroll: true });
      }
    }, 0);
  };

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
      if (payload === undefined) setText("");
      await load();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : e?.message || "failed");
    } finally {
      setSending(false);
      refocusInput();
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
      // Let axios set its own multipart Content-Type (with boundary).
      await api.post("/channel/inbound-video", form);
      await load();
    } catch (e2) {
      const detail = e2?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : e2?.message || "upload failed");
    } finally {
      setUploading(false);
      if (videoInputRef.current) videoInputRef.current.value = "";
      refocusInput();
    }
  };

  /* Stage 2 — Item A. The quick-reply bar is derived EXCLUSIVELY from
     the latest outbound message with a `question_type`. If there is no
     such message, the bar is hidden entirely (no empty row). */
  const quickReplies = useMemo(() => {
    const q = latestQuestion(messages);
    if (!q) return [];
    const payload = q.question_payload || {};
    if (q.question_type === "skill_menu") {
      const skills = Array.isArray(payload.skills) ? payload.skills : [];
      return skills.map((s) => ({ label: `${s.n}. ${s.title}`, send: String(s.n) }));
    }
    if (q.question_type === "step") {
      const label = (payload.next_label || "Next").trim();
      return [{ label, send: label }];
    }
    if (q.question_type === "quiz") {
      const options = Array.isArray(payload.options) ? payload.options : [];
      return options.map((o) => ({ label: `${o.n}. ${o.text}`, send: String(o.n) }));
    }
    return [];
  }, [messages]);

  return (
    <div className="h-full flex flex-col" data-testid="caregiver-chat-page">
      {/* Thread */}
      <section
        ref={scrollRef}
        onScroll={onThreadScroll}
        data-testid="chat-thread"
        className="flex-1 px-4 py-4 space-y-2 overflow-y-auto"
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

      {/* Composer. No padding below — sits directly above the fixed nav. */}
      <section
        className="px-3 pt-3 pb-2 border-t"
        style={{
          borderColor: "var(--fs-border)",
          background: "var(--fs-surface)",
        }}
      >
        {quickReplies.length > 0 ? (
          <div
            className="flex flex-wrap gap-2 mb-2"
            data-testid="quickreplies"
          >
            {quickReplies.map((q, i) => (
              <button
                key={`${q.label}-${i}`}
                type="button"
                onClick={() => sendText(q.send)}
                disabled={sending}
                data-testid={`quickreply-${i}`}
                className="tap px-3 rounded-full text-sm font-ui border"
                style={{
                  borderColor: "var(--fs-border)",
                  color: "var(--fs-fg)",
                }}
              >
                {q.label}
              </button>
            ))}
          </div>
        ) : null}
        <div className="flex items-end gap-2">
          <textarea
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKey}
            disabled={sending || uploading}
            rows={1}
            placeholder={COMPOSER_PLACEHOLDER[lang] || COMPOSER_PLACEHOLDER.en}
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
