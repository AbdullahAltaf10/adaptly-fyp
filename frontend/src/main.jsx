import { StrictMode } from "react";
import { createRoot } from "react-dom/client";

import App from "./App.jsx";
import { AuthProvider } from "./auth/AuthContext";
import "./index.css";

// StrictMode double-invokes effects in development on purpose, to surface
// effects that do not clean up after themselves. The engagement capture loop
// is written to survive it - see src/engagement/useEngagementCapture.js.
createRoot(document.getElementById("root")).render(
  <StrictMode>
    <AuthProvider>
      <App />
    </AuthProvider>
  </StrictMode>
);
