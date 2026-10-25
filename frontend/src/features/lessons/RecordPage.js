import React, { useMemo, useRef, useState } from "react";
import { useNavigate, Link } from "react-router-dom";
import { api } from "@/api";
import { useRole, canRecordSkill } from "@/hooks/useRole";

const MAX_BYTES = 300 * 1024 * 1024;
const MAX_DURATION_S = 120;
const ACCEPT = "video/mp4,video/quicktime,video/webm";

async function probeDuration(file) {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const v = document.createElement("video");
    v.preload = "metadata";
    v.onloadedmetadata = () => {
      URL.revokeObjectURL(url);
      resolve(v.duration || 0);
    };
    v.onerror = () => {
      URL.revokeObjectURL(url);
      resolve(0);
    };
    v.src = url;
  });
}

export default function RecordPage() {
  const nav = useNavigate();
  const role = useRole();
  const allowed = canRecordSkill(role);
  const [file, setFile] = useState(null);
  const [sourceCredit, setSourceCredit] = useState("");
  const [err, setErr] = useState(null);
  const [progress, setProgress] = useState(null); // null | {sent, total, phase}
  const inputRef = useRef(null);

  const canSubmit = useMemo(() => file && !progress && !err, [file, progress, err]);

  const onPick = async (e) => {
    setErr(null);
    const f = e.target.files && e.target.files[0];
    if (!f) {
      setFile(null);
      return;
    }
    if (!["video/mp4", "video/quicktime", "video/webm"].includes(f.type)) {
      setErr(`Unsupported type: ${f.type || "unknown"}. Use mp4, mov or webm.`);
      setFile(null);
      return;
    }
    if (f.size > MAX_BYTES) {
      setErr(`Too big: ${(f.size / 1024 / 1024).toFixed(1)} MB (max 300 MB).`);
      setFile(null);
      return;
    }
    const dur = await probeDuration(f);
    if (dur > MAX_DURATION_S + 0.5) {
      setErr(`Too long: ${dur.toFixed(1)}s (max ${MAX_DURATION_S}s).`);
      setFile(null);
      return;
    }
    setFile(f);
  };

  const onUpload = async () => {
    if (!file) return;
    setErr(null);
    try {
      // Init.
      setProgress({ sent: 0, total: file.size, phase: "init" });
      const init = await api.post("/lessons/uploads", {
        filename: file.name,
        size: file.size,
        content_type: file.type,
      });
      const { upload_id, chunk_size } = init.data;

      // Chunks.
      let offset = 0;
      let index = 0;
      while (offset < file.size) {
        const end = Math.min(offset + chunk_size, file.size);
        const slice = file.slice(offset, end);
        const buf = await slice.arrayBuffer();
        // Use raw PUT with ArrayBuffer; axios will send as-is.
        await api.put(
          `/lessons/uploads/${upload_id}/chunks/${index}`,
          buf,
          { headers: { "Content-Type": "application/octet-stream" } },
        );
        offset = end;
        index += 1;
        setProgress({ sent: offset, total: file.size, phase: "chunks" });
      }

      // Complete.
      setProgress({ sent: file.size, total: file.size, phase: "assembling" });
      const done = await api.post(`/lessons/uploads/${upload_id}/complete`, {
        source_credit: sourceCredit || "",
      });
      const jobId = done.data.job_id;
      nav(`/skills/drafts/${jobId}`);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      setErr(typeof detail === "string" ? detail : e?.message || "upload failed");
      setProgress(null);
    }
  };

  if (!allowed) {
    return (
      <section className="space-y-3" data-testid="record-page-gate">
        <h1 className="text-2xl font-semibold">Record a skill</h1>
        <p
          className="text-sm font-ui fs-card px-4 py-3"
          style={{ color: "var(--fs-muted)" }}
        >
          Switch to Care Manager or Trainer to record skills.
        </p>
      </section>
    );
  }

  const pct = progress ? Math.floor((progress.sent / Math.max(1, progress.total)) * 100) : 0;

  return (
    <section className="space-y-5" data-testid="record-page">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Record a skill</h1>
          <p className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
            Upload a short video (≤2:00). We'll compress, analyze, and extract frames.
          </p>
        </div>
        <Link
          to="/skills"
          data-testid="back-to-skills"
          className="tap text-sm font-ui"
          style={{ color: "var(--fs-muted)" }}
        >
          Cancel
        </Link>
      </header>

      <div className="fs-card p-4 space-y-4">
        <label className="block space-y-2">
          <span className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
            Video file
          </span>
          <input
            ref={inputRef}
            type="file"
            accept={ACCEPT}
            onChange={onPick}
            disabled={!!progress}
            data-testid="record-file-input"
            className="block w-full text-sm font-ui tap"
          />
          {file ? (
            <p className="text-xs font-ui" style={{ color: "var(--fs-muted)" }}>
              {file.name} — {(file.size / 1024 / 1024).toFixed(1)} MB
            </p>
          ) : null}
        </label>

        <label className="block space-y-2">
          <span className="text-sm font-ui" style={{ color: "var(--fs-muted)" }}>
            Source credit (optional)
          </span>
          <input
            type="text"
            value={sourceCredit}
            onChange={(e) => setSourceCredit(e.target.value)}
            placeholder="Chippewa Valley Technical College, CC BY 4.0, edited"
            disabled={!!progress}
            data-testid="record-source-credit"
            className="block w-full text-sm font-ui rounded-md px-3 py-2 border bg-transparent tap"
            style={{ borderColor: "var(--fs-border)" }}
          />
        </label>

        {err ? (
          <p
            data-testid="record-error"
            className="text-sm"
            style={{ color: "var(--fs-fail)" }}
          >
            {err}
          </p>
        ) : null}

        {progress ? (
          <div data-testid="record-progress" className="space-y-2">
            <div
              className="w-full h-2 rounded-full overflow-hidden"
              style={{ background: "var(--fs-accent)" }}
            >
              <div
                data-testid="record-progress-bar"
                className="h-full"
                style={{
                  width: `${pct}%`,
                  background: "var(--fs-primary)",
                  transition: "width 150ms linear",
                }}
              />
            </div>
            <p
              className="text-xs font-ui"
              style={{ color: "var(--fs-muted)" }}
              data-testid="record-progress-text"
            >
              {progress.phase === "assembling"
                ? "Assembling on server…"
                : `${pct}% uploaded`}
            </p>
          </div>
        ) : null}

        <button
          type="button"
          onClick={onUpload}
          disabled={!canSubmit}
          data-testid="record-upload-btn"
          className="tap px-5 rounded-full font-ui text-sm w-full"
          style={{
            background: canSubmit ? "var(--fs-primary)" : "var(--fs-accent)",
            color: canSubmit ? "var(--fs-primary-fg)" : "var(--fs-muted)",
          }}
        >
          {progress ? "Uploading…" : "Upload"}
        </button>
      </div>
    </section>
  );
}
