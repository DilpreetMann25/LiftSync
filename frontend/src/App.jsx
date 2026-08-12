/** Routing and the authentication gate. */

import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Auth from "./pages/Auth";
import Dashboard from "./pages/Dashboard";
import Progress from "./pages/Progress";
import LogWorkout from "./pages/LogWorkout";
import Coach from "./pages/Coach";
import { Spinner } from "./components/ui";

function Gate() {
  const { user, loading } = useAuth();

  // While the stored token is being verified, render nothing but a
  // spinner. Skipping this makes the login screen flash on every
  // refresh before the session resolves.
  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <Spinner size={24} className="text-ink-600" />
      </div>
    );
  }

  if (!user) return <Auth />;

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/progress" element={<Progress />} />
        <Route path="/log" element={<LogWorkout />} />
        <Route path="/coach" element={<Coach />} />
        {/* Anything unrecognised goes home rather than showing a blank
            page -- a 404 inside an app the user is already signed into
            is almost always a stale link. */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Gate />
      </AuthProvider>
    </BrowserRouter>
  );
}
