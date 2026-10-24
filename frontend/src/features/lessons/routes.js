import React from "react";
import SkillsPage from "./SkillsPage";
import CaregiverLessonsPage from "./CaregiverLessonsPage";

export const routes = [
  { path: "/skills", element: <SkillsPage /> },
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
