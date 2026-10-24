import React from "react";
import ChatPage from "./ChatPage";

// Caregiver-only feature. No agency-side routes.
export const routes = [{ path: "/c/:code", element: <ChatPage /> }];

export const nav = [
  { label: "Chat", path: "/c/:code", order: 10, side: "caregiver" },
];
