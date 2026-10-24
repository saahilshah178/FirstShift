import React from "react";
import TodayPage from "./TodayPage";
import NewHiresPage from "./NewHiresPage";
import ClientsPage from "./ClientsPage";

export const routes = [
  { path: "/today", element: <TodayPage /> },
  { path: "/new-hires", element: <NewHiresPage /> },
  { path: "/clients", element: <ClientsPage /> },
];

export const nav = [
  { label: "Today", path: "/today", order: 10, side: "agency" },
  { label: "New hires", path: "/new-hires", order: 30, side: "agency" },
  { label: "Clients", path: "/clients", order: 50, side: "agency" },
];
