import { useEffect, useMemo, useState } from "react";

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

/**
 * Single source of truth for role capabilities. Mirrors the backend
 * matrix in `backend/roles.py` + CONTRACTS §11. Scattered
 * `canSignoff(role)` call-sites across pages were drifting; this
 * object collapses them to one place.
 *
 * Return shape: `{role, can: {editSkills, signOff, nearMiss, archive,
 * replaceSource, recordSkill, answerQuestions, publish, addQuestion}}`.
 */
export function useCaps() {
  const role = useRole();
  const can = useMemo(
    () => ({
      // Agency write capabilities. Server mirrors each flag; the UI
      // uses them to hide buttons so a Scheduler never even sees the
      // control. If a Trainer or Scheduler forges the header, the
      // backend 403s and the ForbiddenToast fires.
      editSkills:       role === CARE_MANAGER || role === TRAINER,
      recordSkill:      role === CARE_MANAGER || role === TRAINER,
      publish:          role === CARE_MANAGER || role === TRAINER,
      addQuestion:      role === CARE_MANAGER || role === TRAINER,
      signOff:          role === CARE_MANAGER,
      nearMiss:         role === CARE_MANAGER,
      archive:          role === CARE_MANAGER,
      replaceSource:    role === CARE_MANAGER,
      answerQuestions:  role === CARE_MANAGER,
    }),
    [role],
  );
  return { role, can };
}

// Legacy predicates — kept because older imports are still live.
// Prefer `useCaps().can.X` in new code; refactoring in situ.
export const canSignoff = (role) => role === CARE_MANAGER;
export const canAnswerQuestions = (role) => role === CARE_MANAGER;
export const canArchiveSkill = (role) => role === CARE_MANAGER;
export const canEditSkill = (role) => role === CARE_MANAGER || role === TRAINER;
export const canRecordSkill = (role) =>
  role === CARE_MANAGER || role === TRAINER;
