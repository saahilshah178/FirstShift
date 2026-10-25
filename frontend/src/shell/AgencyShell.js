import React, { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { agencyNav } from "@/featureRegistry";
import { api, setForbiddenHandler } from "@/api";
import { ROLES, writeRole } from "@/hooks/useRole";
import { ToastProvider, useForbiddenToast } from "@/shell/Toasts";
import { X, UserRound } from "lucide-react";

const ROLE_KEY = "firstshift.agency_role";

export default function AgencyShell({ children, nav }) {
  const navItems = agencyNav(nav);
  const location = useLocation();
  const [role, setRole] = useState(
    () => localStorage.getItem(ROLE_KEY) || "Care Manager",
  );
  const [showCaregiverPicker, setShowCaregiverPicker] = useState(false);

  useEffect(() => {
    writeRole(role);
  }, [role]);

  return (
    <ToastProvider>
      <ForbiddenToastBridge />
      <div className="fs-frame" data-side="agency" data-testid="agency-shell">
        <TopBar
          role={role}
          onRoleChange={setRole}
          onOpenPicker={() => setShowCaregiverPicker(true)}
        />
        <main className="flex-1 px-5 py-5 pb-24" data-testid="agency-main">
          {children}
        </main>
        <BottomNav items={navItems} currentPath={location.pathname} />
        {showCaregiverPicker ? (
          <CaregiverPicker onClose={() => setShowCaregiverPicker(false)} />
        ) : null}
      </div>
    </ToastProvider>
  );
}

/**
 * Hook into the api 403 interceptor so the toast provider in this
 * subtree receives the forbidden notification. Lives inside the
 * provider so `useToasts()` resolves.
 */
function ForbiddenToastBridge() {
  const showForbidden = useForbiddenToast();
  useEffect(() => {
    setForbiddenHandler(showForbidden);
    return () => setForbiddenHandler(null);
  }, [showForbidden]);
  return null;
}

function TopBar({ role, onRoleChange, onOpenPicker }) {
  return (
    <header
      className="sticky top-0 z-20 border-b"
      style={{ borderColor: "var(--fs-border)", background: "var(--fs-bg)" }}
      data-testid="agency-topbar"
    >
      <div className="flex items-center justify-between px-5 py-3">
        <Link
          to="/"
          data-testid="brand-link"
          className="flex items-baseline gap-2"
        >
          <span className="text-xl font-semibold tracking-tight">
            FirstShift
          </span>
          <span
            className="text-xs font-ui"
            style={{ color: "var(--fs-muted)" }}
          >
            Agency
          </span>
        </Link>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={onOpenPicker}
            data-testid="open-caregiver-picker"
            className="tap font-ui text-sm px-3 rounded-full border"
            style={{ borderColor: "var(--fs-border)" }}
          >
            <UserRound size={16} className="mr-1" />
            Caregivers
          </button>
          <RoleSwitch value={role} onChange={onRoleChange} />
        </div>
      </div>
    </header>
  );
}

function RoleSwitch({ value, onChange }) {
  return (
    <label className="relative" data-testid="role-switch-wrap">
      <span className="sr-only">Role</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid="role-switch"
        className="tap font-ui text-sm pl-3 pr-8 rounded-full appearance-none bg-transparent border"
        style={{ borderColor: "var(--fs-border)", color: "var(--fs-fg)" }}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>
      <span
        aria-hidden
        className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 text-xs"
        style={{ color: "var(--fs-muted)" }}
      >
        ▾
      </span>
    </label>
  );
}

function BottomNav({ items, currentPath }) {
  return (
    <nav
      data-testid="agency-nav"
      className="fixed bottom-0 left-1/2 -translate-x-1/2 w-full border-t"
      style={{
        maxWidth: "var(--fs-max-w)",
        background: "var(--fs-surface)",
        borderColor: "var(--fs-border)",
      }}
    >
      <ul className="grid grid-cols-7 font-ui text-[11px]">
        {items.map((n) => (
          <li key={n.path}>
            <NavLink
              to={n.path}
              data-testid={`nav-${n.path.replace(/^\//, "")}`}
              className={({ isActive }) =>
                [
                  "flex flex-col items-center justify-center h-14 px-1 text-center leading-tight",
                  isActive
                    ? "text-[color:var(--fs-primary)] font-semibold"
                    : "text-[color:var(--fs-muted)]",
                ].join(" ")
              }
            >
              {n.label}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function CaregiverPicker({ onClose }) {
  const navigate = useNavigate();
  const [rows, setRows] = useState(null);
  const [err, setErr] = useState(null);

  useEffect(() => {
    api
      .get("/caregivers/list")
      .then((r) => setRows(r.data.caregivers))
      .catch((e) => setErr(e?.message || "failed to load"));
  }, []);

  // a11y: Escape closes the modal. Scoped to this component (unmounts
  // when the dialog closes) so it doesn't fight other listeners.
  useEffect(() => {
    const onKey = (e) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-30 flex items-end sm:items-center justify-center"
      style={{ background: "rgba(28,22,17,0.55)" }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="caregiver-picker-title"
      data-testid="caregiver-picker"
      onClick={(e) => {
        // Click on backdrop (not the inner card) also closes.
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className="w-full sm:rounded-xl sm:max-w-md fs-card border-t sm:border"
        style={{ borderColor: "var(--fs-border)" }}
      >
        <div
          className="flex items-center justify-between px-5 py-3 border-b"
          style={{ borderColor: "var(--fs-border)" }}
        >
          <h2
            id="caregiver-picker-title"
            className="text-lg font-semibold"
          >
            Open caregiver view
          </h2>
          <button
            type="button"
            onClick={onClose}
            data-testid="caregiver-picker-close"
            aria-label="Close caregiver picker"
            className="tap rounded-full"
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        <div className="px-2 py-2 max-h-[70vh] overflow-y-auto fs-divider">
          {err ? (
            <p className="text-sm px-3 py-4" style={{ color: "var(--fs-fail)" }}>
              {err}
            </p>
          ) : rows === null ? (
            <p
              className="text-sm px-3 py-4"
              style={{ color: "var(--fs-muted)" }}
            >
              Loading…
            </p>
          ) : (
            rows.map((c) => (
              <button
                key={c.id}
                type="button"
                data-testid={`caregiver-row-${c.access_code}`}
                onClick={() => {
                  onClose();
                  navigate(`/c/${c.access_code}`);
                }}
                className="w-full text-left px-3 py-3 flex items-center justify-between tap"
              >
                <div>
                  <div className="font-semibold">{c.name}</div>
                  <div
                    className="text-xs font-ui"
                    style={{ color: "var(--fs-muted)" }}
                  >
                    {c.agency_name} • {c.language.toUpperCase()}
                  </div>
                </div>
                <code
                  className="font-ui text-sm tracking-wider px-2 py-1 rounded"
                  style={{ background: "var(--fs-accent)" }}
                >
                  {c.access_code}
                </code>
              </button>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
