import { Routes, Route, Navigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Layout from "@/components/Layout";
import Login from "@/pages/Login";
import Swipe from "@/pages/Swipe";
import Favorites from "@/pages/Favorites";
import FavoriteDetail from "@/pages/FavoriteDetail";
import Archives from "@/pages/Archives";
import Settings from "@/pages/Settings";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { token, loading } = useAuth();
  if (loading) return <div className="flex h-screen items-center justify-center">Loading...</div>;
  if (!token) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/swipe" element={<Swipe />} />
        <Route path="/favorites" element={<Favorites />} />
        <Route path="/favorites/:id" element={<FavoriteDetail />} />
        <Route path="/archives" element={<Archives />} />
        <Route path="/settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<Navigate to="/swipe" replace />} />
    </Routes>
  );
}
