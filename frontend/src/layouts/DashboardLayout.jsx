import { signOut } from "firebase/auth";
import { useNavigate } from "react-router-dom";
import { auth } from "../firebase/config";
import { useAuth } from "../context/AuthContext";

const FONT_SIZE_MAP = { small: "14px", medium: "16px", large: "20px" };

export default function DashboardLayout({ title, children }) {
  const navigate = useNavigate();
  const { currentUser, profile } = useAuth();

  const handleLogout = async () => {
    await signOut(auth);
    navigate("/login");
  };

  const settings = profile?.accessibility_settings || {};
  const wrapperStyle = {
    fontFamily: settings.font_family === "dyslexia-friendly" ? "'Lexend', sans-serif" : "sans-serif",
    fontSize: FONT_SIZE_MAP[settings.font_size] || "16px",
    backgroundColor: settings.contrast === "high" ? "#000" : "#fff",
    color: settings.contrast === "high" ? "#fff" : "#000",
    minHeight: "100vh",
    width: "100%",
    boxSizing: "border-box",
  };

  return (
    <div style={wrapperStyle}>
      <nav style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "1rem 2rem", borderBottom: "1px solid #ddd" }}>
        <strong>Adaptly</strong>
        <div>
          <a href="/settings" style={{ marginRight: "1rem", color: "inherit" }}>Settings</a>
          <span style={{ marginRight: "1rem" }}>
            {currentUser?.email} ({profile?.mode}{profile?.corporate_role ? ` / ${profile.corporate_role}` : ""})
          </span>
          <button onClick={handleLogout}>Logout</button>
        </div>
      </nav>
      <main style={{ padding: "2rem" }}>
        <h2>{title}</h2>
        {children}
      </main>
    </div>
  );
}