import { useEffect, useState } from "react";

/**
 * Agency role mirror of `localStorage.getItem('firstshift.agency_role')`.
 *
 * Why a custom hook: the role switch in `AgencyShell` writes to
 * localStorage inside its own component state. Sibling pages read the
 * role on mount — without this hook, flipping the switch wouldn't
 * re-render buttons on pages that are already mounted.
 *
 * We subscribe to a custom `firstshift:role` event in addition to the
 * native `storage` event (which only fires in OTHER tabs). The
 * `AgencyShell` dispatches that event whenever it writes the key.
 */
const KEY = "firstshift.agency_role";
const EVENT = "firstshift:role";

export const ROLES = ["Care Manager", "Trainer", "Scheduler"];
export const CARE_MANAGER = "Care Manager";
export const TRAINER = "Trainer";
export const SCHEDULER = "Scheduler";

function readRole() {
  try {
    return localStorage.getItem(KEY) || CARE_MANAGER;
  } catch {
    return CARE_MANAGER;
  }
}

export function useRole() {
  const [role, setRole] = useState(readRole);
  useEffect(() => {
    const onCustom = (e) => setRole(e.detail || readRole());
    const onStorage = (e) => {
      if (e.key === KEY) setRole(readRole());
    };
    window.addEventListener(EVENT, onCustom);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(EVENT, onCustom);
      window.removeEventListener("storage", onStorage);
    };
  }, []);
  return role;
}

/** Write the role and notify same-tab listeners. */
export function writeRole(next) {
  try {
    localStorage.setItem(KEY, next);
    window.dispatchEvent(new CustomEvent(EVENT, { detail: next }));
  } catch {
    /* ignored — localStorage may be denied in private mode */
  }
}

/** Convenience: current role can do X. */
export const canSignoff = (role) => role === CARE_MANAGER;
export const canAnswerQuestions = (role) => role === CARE_MANAGER;
export const canArchiveSkill = (role) => role === CARE_MANAGER;
export const canEditSkill = (role) => role === CARE_MANAGER || role === TRAINER;
export const canRecordSkill = (role) =>
  role === CARE_MANAGER || role === TRAINER;
