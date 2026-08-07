import { Routes, Route, Navigate } from "react-router-dom";
import Login from "./pages/Login";
import Register from "./pages/Register";
import LearnerDashboard from "./pages/LearnerDashboard";
import EmployeeDashboard from "./pages/EmployeeDashboard";
import HRDashboard from "./pages/HRDashboard";
import ProtectedRoute from "./routes/ProtectedRoute";
import PublicRoute from "./routes/PublicRoute";
import UploadContent from "./pages/UploadContent";
import AccessibilitySettings from "./pages/AccessibilitySettings";
import StudySession from "./pages/StudySession";

function App() {
  return (
    <Routes>
      <Route path="/session" element={<ProtectedRoute><StudySession /></ProtectedRoute>} />
      <Route path="/" element={<Navigate to="/login" />} />
      <Route path="/login" element={<PublicRoute><Login /></PublicRoute>} />
      <Route path="/register" element={<PublicRoute><Register /></PublicRoute>} />
      <Route path="/learner" element={
        <ProtectedRoute allowedMode="learner"><LearnerDashboard /></ProtectedRoute>
      } />
      <Route path="/employee" element={
        <ProtectedRoute allowedMode="corporate" allowedRole="employee"><EmployeeDashboard /></ProtectedRoute>
      } />
      <Route path="/hr" element={
        <ProtectedRoute allowedMode="corporate" allowedRole="hr_admin"><HRDashboard /></ProtectedRoute>
      } />
      <Route path="/upload" element={<ProtectedRoute><UploadContent /></ProtectedRoute>} />
      <Route path="/settings" element={<ProtectedRoute><AccessibilitySettings /></ProtectedRoute>} />
    </Routes>
  );
}

export default App;