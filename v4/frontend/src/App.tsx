import { Route, Routes, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { HomeFeed } from "@/pages/HomeFeed";
import { Companies } from "@/pages/Companies";
import { Company } from "@/pages/Company";
import { CompanyEvents } from "@/pages/CompanyEvents";
import { EventDetail } from "@/pages/EventDetail";
import { Signals } from "@/pages/Signals";
import { SignalDetail } from "@/pages/SignalDetail";
import { DocumentPage } from "@/pages/DocumentPage";

export default function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<HomeFeed />} />
        <Route path="/companies" element={<Companies />} />
        <Route path="/company/:ticker" element={<Company />} />
        <Route path="/company/:ticker/events" element={<CompanyEvents />} />
        <Route path="/company/:ticker/event/:eventId" element={<EventDetail />} />
        <Route path="/signals" element={<Signals />} />
        <Route path="/signals/:signalId" element={<SignalDetail />} />
        <Route path="/documents/:documentId" element={<DocumentPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
