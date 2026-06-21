import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { LoginPage } from "@/pages/LoginPage";
import { SignupPage } from "@/pages/SignupPage";
import { HomePage } from "@/pages/HomePage";
import { WatchlistPage } from "@/pages/WatchlistPage";
import { CompaniesPage } from "@/pages/CompaniesPage";
import { CompanyPage } from "@/pages/CompanyPage";
import { CompanyEventsPage } from "@/pages/CompanyEventsPage";
import { EventDetailPage } from "@/pages/EventDetailPage";
import { IntelligenceObjectPage } from "@/pages/IntelligenceObjectPage";
import { SignalDetailPage } from "@/pages/SignalDetailPage";
import { SignalsPage } from "@/pages/SignalsPage";
import { SearchPage } from "@/pages/SearchPage";
import { DocumentPage } from "@/pages/DocumentPage";
import { AdminIngestPage } from "@/pages/AdminIngestPage";
import { AdminReviewPage } from "@/pages/AdminReviewPage";
import { useAuthStore } from "@/store/auth";

function RequireAuth({ children }: { children: JSX.Element }) {
  const { token } = useAuthStore();
  if (!token) return <Navigate to="/login" replace />;
  return children;
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/signup" element={<SignupPage />} />
      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route path="/" element={<HomePage />} />
        <Route path="/watchlist" element={<WatchlistPage />} />
        <Route path="/companies" element={<CompaniesPage />} />
        <Route path="/company/:symbol" element={<CompanyPage />} />
        <Route path="/company/:symbol/events" element={<CompanyEventsPage />} />
        <Route path="/company/:symbol/event/:eventId" element={<EventDetailPage />} />
        <Route path="/signals" element={<SignalsPage />} />
        <Route path="/signals/:signalId" element={<SignalDetailPage />} />
        <Route path="/intelligence/:objectId" element={<IntelligenceObjectPage />} />
        <Route path="/search" element={<SearchPage />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
        <Route path="/admin/ingest" element={<AdminIngestPage />} />
        <Route path="/admin/review" element={<AdminReviewPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
