import { useState, useEffect } from "react";
import api from "../api/client";
import { useAuth } from "../context/AuthContext";
import DashboardLayout from "../layouts/DashboardLayout";

export default function AccessibilitySettings() {
  const { profile, refreshProfile } = useAuth();
  const [fontSize, setFontSize] = useState("medium");
  const [contrast, setContrast] = useState("normal");
  const [fontFamily, setFontFamily] = useState("default");
  const [status, setStatus] = useState("");

  useEffect(() => {
    if (profile?.accessibility_settings) {
      setFontSize(profile.accessibility_settings.font_size || "medium");
      setContrast(profile.accessibility_settings.contrast || "normal");
      setFontFamily(profile.accessibility_settings.font_family || "default");
    }
  }, [profile]);

  const handleSave = async (e) => {
    e.preventDefault();
    setStatus("Saving...");
    try {
      await api.put("/users/me", {
        accessibility_settings: { font_size: fontSize, contrast: contrast, font_family: fontFamily },
      });
      await refreshProfile();
      setStatus("Saved and applied.");
    } catch (err) {
      setStatus(err.response?.data?.detail || "Save failed");
    }
  };

  return (
    <DashboardLayout title="Accessibility Settings">
      <form onSubmit={handleSave} style={{ maxWidth: 400 }}>
        <label style={{ display: "block", marginBottom: "1rem" }}>
          Font Size:
          <select value={fontSize} onChange={(e) => setFontSize(e.target.value)} style={{ display: "block", marginTop: "0.3rem", padding: "0.4rem" }}>
            <option value="small">Small</option>
            <option value="medium">Medium</option>
            <option value="large">Large</option>
          </select>
        </label>

        <label style={{ display: "block", marginBottom: "1rem" }}>
          Contrast:
          <select value={contrast} onChange={(e) => setContrast(e.target.value)} style={{ display: "block", marginTop: "0.3rem", padding: "0.4rem" }}>
            <option value="normal">Normal</option>
            <option value="high">High Contrast</option>
          </select>
        </label>

        <label style={{ display: "block", marginBottom: "1rem" }}>
          Font Style:
          <select value={fontFamily} onChange={(e) => setFontFamily(e.target.value)} style={{ display: "block", marginTop: "0.3rem", padding: "0.4rem" }}>
            <option value="default">Default</option>
            <option value="dyslexia-friendly">Dyslexia-Friendly (Lexend)</option>
          </select>
        </label>

        <button type="submit">Save Settings</button>
      </form>
      {status && <p style={{ marginTop: "1rem" }}>{status}</p>}
    </DashboardLayout>
  );
}