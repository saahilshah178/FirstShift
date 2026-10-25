import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

/**
 * Minimal toast system scoped to the agency shell.
 *
 * Why not sonner? sonner is in package.json but ships with next-themes
 * via the shadcn wrapper (not usable here) and we only need two
 * variants + no actions. ~60 lines of our own is simpler to reason
 * about + themed via the design tokens.
 */
const ToastCtx = createContext(null);

const AUTO_DISMISS_MS = 4500;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const idRef = useRef(0);

  const show = useCallback((opts) => {
    const id = ++idRef.current;
    const t = {
      id,
      variant: opts.variant || "default",
      title: opts.title || "",
      description: opts.description || "",
    };
    setToasts((prev) => [...prev, t]);
    const ms = opts.durationMs || AUTO_DISMISS_MS;
    if (ms > 0) {
      setTimeout(() => {
        setToasts((prev) => prev.filter((x) => x.id !== id));
      }, ms);
    }
    return id;
  }, []);

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((x) => x.id !== id));
  }, []);

  return (
    <ToastCtx.Provider value={{ show, dismiss }}>
      {children}
      <ToastViewport toasts={toasts} onDismiss={dismiss} />
    </ToastCtx.Provider>
  );
}

export function useToasts() {
  const v = useContext(ToastCtx);
  if (!v) {
    throw new Error("useToasts must be used inside <ToastProvider>");
  }
  return v;
}

function ToastViewport({ toasts, onDismiss }) {
  if (!toasts || toasts.length === 0) return null;
  return (
    <div
      data-testid="toast-viewport"
      className="fixed z-40 bottom-20 left-1/2 -translate-x-1/2 w-full px-4 flex flex-col gap-2 pointer-events-none"
      style={{ maxWidth: "var(--fs-max-w)" }}
    >
      {toasts.map((t) => (
        <Toast key={t.id} toast={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  );
}

function Toast({ toast, onDismiss }) {
  const warn = toast.variant === "warn";
  const fail = toast.variant === "fail";
  const borderColor = fail
    ? "var(--fs-fail)"
    : warn
      ? "var(--fs-warn)"
      : "var(--fs-primary)";
  return (
    <div
      role="status"
      data-testid={`toast-${toast.variant}`}
      data-toast-id={toast.id}
      className="pointer-events-auto fs-card px-4 py-3 shadow-md"
      style={{
        borderLeft: `3px solid ${borderColor}`,
      }}
      onClick={onDismiss}
    >
      {toast.title ? (
        <p className="text-sm font-semibold" data-testid="toast-title">
          {toast.title}
        </p>
      ) : null}
      {toast.description ? (
        <p
          className="text-xs font-ui mt-0.5"
          style={{ color: "var(--fs-muted)" }}
          data-testid="toast-description"
        >
          {toast.description}
        </p>
      ) : null}
    </div>
  );
}

/**
 * Convenience hook that pipes an `onForbidden` payload from
 * `api.setForbiddenHandler(...)` into a canned toast.
 */
export function useForbiddenToast() {
  const { show } = useToasts();
  return useCallback(
    (payload) => {
      const allowed = (payload && payload.allowed) || [];
      show({
        variant: "warn",
        title: "Your role doesn't allow this action.",
        description: allowed.length
          ? `Allowed: ${allowed.join(", ")}.`
          : "Switch roles to continue.",
      });
    },
    [show],
  );
}
