import { useEffect, useState } from "react";
import api from "../api/client";
import DashboardLayout from "../layouts/DashboardLayout";
import { Link } from "react-router-dom";

export default function LearnerDashboard() {
  const [content, setContent] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => {
    const fetchContent = async () => {
      try {
        const res = await api.get("/content/list");
        setContent(res.data);
      } catch (err) {
        // previously this threw into an unhandled promise rejection and the
        // list just silently stayed empty
        setError(err.response?.data?.detail || "Could not load your content.");
      }
    };
    fetchContent();
  }, []);

  return (
    <DashboardLayout title="Learner Dashboard">
      <Link to="/upload">+ Upload New Content</Link>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <ul style={{ marginTop: "1rem" }}>
        {content.map((item) => (
          <li key={item._id}>
            {item.title} — {item.type} ({item.status})
          </li>
        ))}
      </ul>
    </DashboardLayout>
  );
}