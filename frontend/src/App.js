import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { discoverFeatures } from "@/featureRegistry";
import AgencyShell from "@/shell/AgencyShell";
import CaregiverLayout from "@/shell/CaregiverLayout";
import "@/App.css";

const { agencyRoutes, caregiverRoutes, nav } = discoverFeatures();

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Caregiver side — chat-shaped layout, driven by access code */}
        <Route path="/c/:code" element={<CaregiverLayout nav={nav} />}>
          {caregiverRoutes.map((r) => (
            <Route
              key={r.subpath || "index"}
              {...(r.subpath ? { path: r.subpath } : { index: true })}
              element={r.element}
            />
          ))}
        </Route>

        {/* Agency root — redirect to Today, the default view. */}
        <Route path="/" element={<Navigate to="/today" replace />} />

        {/* Agency pages (auto-discovered from features) */}
        {agencyRoutes.map((r) => (
          <Route
            key={r.path}
            path={r.path}
            element={<AgencyShell nav={nav}>{r.element}</AgencyShell>}
          />
        ))}

        <Route
          path="*"
          element={
            <AgencyShell nav={nav}>
              <div data-testid="not-found" className="py-10 text-center">
                <p style={{ color: "var(--fs-muted)" }}>Page not found.</p>
              </div>
            </AgencyShell>
          }
        />
      </Routes>
    </BrowserRouter>
  );
}
