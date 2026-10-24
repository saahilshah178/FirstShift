import React from "react";
import QuestionsPage from "./QuestionsPage";
import AskPage from "./AskPage";

export const routes = [
  { path: "/questions", element: <QuestionsPage /> },
  { path: "/c/:code/ask", element: <AskPage /> },
];

export const nav = [
  { label: "Questions", path: "/questions", order: 70, side: "agency" },
  { label: "Ask", path: "/c/:code/ask", order: 30, side: "caregiver" },
];
