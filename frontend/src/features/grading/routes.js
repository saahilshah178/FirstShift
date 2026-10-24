import React from "react";
import SignoffPage from "./SignoffPage";
import CompetencyPage from "./CompetencyPage";

export const routes = [
  { path: "/signoff", element: <SignoffPage /> },
  { path: "/competency", element: <CompetencyPage /> },
];

export const nav = [
  { label: "Sign-off", path: "/signoff", order: 40, side: "agency" },
  {
    label: "Competency files",
    path: "/competency",
    order: 60,
    side: "agency",
  },
];
