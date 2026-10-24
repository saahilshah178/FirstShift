import React from "react";
import SkillsPage from "./SkillsPage";
import RecordPage from "./RecordPage";
import DraftEditorPage from "./DraftEditorPage";
import SkillDetailPage from "./SkillDetailPage";
import CaregiverLessonsPage from "./CaregiverLessonsPage";

export const routes = [
  { path: "/skills", element: <SkillsPage /> },
  { path: "/skills/record", element: <RecordPage /> },
  { path: "/skills/drafts/:jobId", element: <DraftEditorPage /> },
  // Must come AFTER the more-specific /skills/* routes so router picks them first.
  { path: "/skills/:skillId", element: <SkillDetailPage /> },
  { path: "/c/:code/lessons", element: <CaregiverLessonsPage /> },
];

export const nav = [
  { label: "Skills", path: "/skills", order: 20, side: "agency" },
  {
    label: "Lessons",
    path: "/c/:code/lessons",
    order: 20,
    side: "caregiver",
  },
];
