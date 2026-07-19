import { Route, Routes, Navigate, useLocation } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { useAuth } from "@/auth/AuthContext";
import { PageLoader } from "@/components/common/Spinner";
import { Login } from "@/pages/Login";
import { ChangePassword } from "@/pages/ChangePassword";
import { Watchlist } from "@/pages/Watchlist";
import { AdminUsers } from "@/pages/AdminUsers";
import { AdminReviews } from "@/pages/AdminReviews";
import { HomeFeed } from "@/pages/HomeFeed";
import { Companies } from "@/pages/Companies";
import { Company } from "@/pages/Company";
import { CompanyEvents } from "@/pages/CompanyEvents";
import { EventDetail } from "@/pages/EventDetail";
import { Signals } from "@/pages/Signals";
import { SignalDetail } from "@/pages/SignalDetail";
import { DocumentPage } from "@/pages/DocumentPage";
import { Profile } from "@/pages/Profile";
import { NotificationResult } from "@/pages/NotificationResult";

function RequireAuth({ children, allowPasswordChange = false }: { children: JSX.Element; allowPasswordChange?: boolean }) {
  const { user, loading } = useAuth();
  const location = useLocation();
  if (loading) return <PageLoader />;
  if (!user) return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  if (user.must_change_password && !allowPasswordChange) return <Navigate to="/change-password" replace />;
  return children;
}

function RequireAdmin({ children }: { children: JSX.Element }) {
  const { user } = useAuth();
  if (user?.role !== "ADMIN") return <Navigate to="/" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/change-password" element={<RequireAuth allowPasswordChange><ChangePassword /></RequireAuth>} />
      <Route path="/notifications/:result" element={<NotificationResult />} />
      <Route element={<RequireAuth><AppShell /></RequireAuth>}>
        <Route path="/" element={<HomeFeed />} />
        <Route path="/watchlist" element={<Watchlist />} />
        <Route path="/profile" element={<Profile />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/company/:ticker" element={<Company />} />
        <Route path="/company/:ticker/events" element={<CompanyEvents />} />
        <Route path="/company/:ticker/event/:eventId" element={<EventDetail />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/signals/:signalId" element={<SignalDetail />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
        <Route path="/admin/users" element={<RequireAdmin><AdminUsers /></RequireAdmin>} />
        <Route path="/admin/reviews" element={<RequireAdmin><AdminReviews /></RequireAdmin>} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
