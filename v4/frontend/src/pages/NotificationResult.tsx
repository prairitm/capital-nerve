import { CheckCircle2, CircleX } from "lucide-react";
import { Link, useParams } from "react-router-dom";

const RESULTS: Record<string, { ok: boolean; title: string; message: string }> = {
  verified: { ok: true, title: "Email verified", message: "Your notification address is ready to receive watchlist updates." },
  unsubscribed: { ok: true, title: "Email alerts disabled", message: "You will no longer receive watchlist update emails. You can enable them again from Profile." },
  "verification-expired": { ok: false, title: "Verification link expired", message: "Open Profile and save your notification address again to receive a new link." },
  "unsubscribe-expired": { ok: false, title: "Link already used", message: "Sign in and open Profile to review your current email settings." },
};

export function NotificationResult() {
  const { result = "" } = useParams();
  const content = RESULTS[result] || RESULTS["verification-expired"];
  const Icon = content.ok ? CheckCircle2 : CircleX;
  return <main className="min-h-screen grid place-items-center px-4"><div className="card w-full max-w-md p-7 text-center"><Icon className={content.ok ? "mx-auto text-positive" : "mx-auto text-negative"} size={36} /><h1 className="mt-4 text-xl font-semibold">{content.title}</h1><p className="mt-2 text-sm text-ink-mute">{content.message}</p><Link className="btn-primary mt-6 inline-flex" to="/profile">Open Profile</Link></div></main>;
}
