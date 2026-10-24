import React from "react";
import SignoffPage from "./SignoffPage";
import SignoffDetailPage from "./SignoffDetailPage";
import CompetencyPage from "./CompetencyPage";
import CompetencyDetailPage from "./CompetencyDetailPage";
import PracticePage from "./PracticePage";
import PracticeResultPage from "./PracticeResultPage";

export const routes = [
  // Agency
  { path: "/signoff", element: <SignoffPage /> },
  { path: "/signoff/:attemptId", element: <SignoffDetailPage /> },
  { path: "/competency", element: <CompetencyPage /> },
  { path: "/competency/:caregiverId", element: <CompetencyDetailPage /> },
  // Caregiver (mounted under /c/:code via the feature registry)
  { path: "/c/:code/practice", element: <PracticePage /> },
  { path: "/c/:code/practice/:attemptId", element: <PracticeResultPage /> },
];

export const nav = [
  { label: "Sign-off", path: "/signoff", order: 40, side: "agency" },
  {
    label: "Competency files",
    path: "/competency",
    order: 60,
    side: "agency",
  },
  // Caregiver nav
  {
    label: "Practice",
    path: "/c/:code/practice",
    order: 15,
    side: "caregiver",
  },
];
