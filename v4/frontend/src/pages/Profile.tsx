import { useEffect, useState } from "react";
import { BellRing, CheckCircle2, Mail, Send } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { Profile as ProfileType } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { PageLoader, Spinner } from "@/components/common/Spinner";

export function Profile() {
  const queryClient = useQueryClient();
  const { refresh } = useAuth();
  const query = useQuery({ queryKey: ["profile"], queryFn: () => api<ProfileType>("/profile") });
  const [form, setForm] = useState<ProfileType | null>(null);
  const [saved, setSaved] = useState(false);
  const [testQueued, setTestQueued] = useState(false);

  useEffect(() => { if (query.data) setForm(query.data); }, [query.data]);

  const save = useMutation({
    mutationFn: () => api<ProfileType>("/profile", {
      method: "PATCH",
      body: {
        full_name: form?.full_name || null,
        notification_email: form?.notification_email,
        email_enabled: form?.email_enabled,
        financial_results_enabled: form?.financial_results_enabled,
        investor_presentations_enabled: form?.investor_presentations_enabled,
        earnings_calls_enabled: form?.earnings_calls_enabled,
      },
    }),
    onSuccess: async (profile) => {
      setForm(profile);
      queryClient.setQueryData(["profile"], profile);
      setSaved(true);
      setTimeout(() => setSaved(false), 3000);
      await refresh();
    },
  });
  const testEmail = useMutation({
    mutationFn: () => api<{ queued: boolean }>("/profile/test-email", { method: "POST" }),
    onSuccess: () => { setTestQueued(true); setTimeout(() => setTestQueued(false), 4000); },
  });

  if (query.isLoading || !form) return <PageLoader />;
  if (query.isError) return <p className="text-sm text-negative" role="alert">{(query.error as Error).message}</p>;
  const destinationChanged = form.notification_email.trim().toLowerCase() !== query.data?.notification_email.trim().toLowerCase();
  const needsVerification = destinationChanged
    ? form.notification_email.trim().toLowerCase() !== form.login_email.trim().toLowerCase()
    : form.verification_required;
  const update = <K extends keyof ProfileType>(key: K, value: ProfileType[K]) => {
    setForm((current) => current ? { ...current, [key]: value } : current);
    setSaved(false);
  };

  return (
    <div className="mx-auto max-w-2xl">
      <div className="mb-6">
        <div className="flex items-center gap-2 text-brand-soft"><BellRing size={20} /><span className="text-xs font-semibold uppercase tracking-wider">Account</span></div>
        <h1 className="mt-2 text-2xl font-semibold">Profile and email alerts</h1>
        <p className="mt-1 text-sm text-ink-mute">Choose where CapitalNerve sends new updates for your watchlist.</p>
      </div>

      <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); save.mutate(); }}>
        <section className="card p-5 space-y-4">
          <h2 className="font-semibold">Profile</h2>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Full name</span><input className="input" maxLength={160} value={form.full_name || ""} onChange={(event) => update("full_name", event.target.value)} /></label>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Login email</span><input className="input opacity-70" type="email" value={form.login_email} readOnly /><span className="mt-1 block text-[11px] text-ink-soft">Your login identifier can only be changed by an administrator.</span></label>
        </section>

        <section className="card p-5 space-y-5">
          <div className="flex items-start justify-between gap-4">
            <div><h2 className="font-semibold">Watchlist email alerts</h2><p className="mt-1 text-xs text-ink-mute">One email after each new filing is completely processed.</p></div>
            <label className="inline-flex cursor-pointer items-center gap-2 text-sm font-medium"><input type="checkbox" className="size-4 accent-blue-500" checked={form.email_enabled} onChange={(event) => update("email_enabled", event.target.checked)} />Enabled</label>
          </div>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Notification email</span><div className="relative"><Mail className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" size={16} /><input className="input pl-10" type="email" required value={form.notification_email} onChange={(event) => update("notification_email", event.target.value)} /></div></label>
          {needsVerification ? <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-3 text-xs text-amber-200">This address must be verified. Save to send or resend the verification email.</div> : <div className="flex items-center gap-2 text-xs text-positive"><CheckCircle2 size={15} />Notification address verified</div>}

          <fieldset className="space-y-2" disabled={!form.email_enabled}>
            <legend className="mb-2 text-xs font-medium text-ink-mute">Send alerts for</legend>
            <Preference checked={form.financial_results_enabled} label="Financial Results" onChange={(value) => update("financial_results_enabled", value)} />
            <Preference checked={form.investor_presentations_enabled} label="Investor Presentations" onChange={(value) => update("investor_presentations_enabled", value)} />
            <Preference checked={form.earnings_calls_enabled} label="Earnings Call Transcripts" onChange={(value) => update("earnings_calls_enabled", value)} />
          </fieldset>

          <div className="flex flex-wrap items-center justify-between gap-3 border-t border-line/60 pt-4">
            <button type="button" className="btn-secondary" disabled={testEmail.isPending || !form.email_verified || destinationChanged} onClick={() => testEmail.mutate()}>{testEmail.isPending ? <Spinner /> : <Send size={15} />}Send test email</button>
            <button className="btn-primary" type="submit" disabled={save.isPending}>{save.isPending && <Spinner />}Save changes</button>
          </div>
          {(save.isError || testEmail.isError) && <p className="text-sm text-negative" role="alert">{((save.error || testEmail.error) as Error).message}</p>}
          {saved && <p className="text-sm text-positive" role="status">Profile saved.</p>}
          {testQueued && <p className="text-sm text-positive" role="status">Test email queued for delivery.</p>}
        </section>
      </form>
    </div>
  );
}

function Preference({ checked, label, onChange }: { checked: boolean; label: string; onChange: (value: boolean) => void }) {
  return <label className="flex items-center gap-3 rounded-xl border border-line/60 px-3 py-2.5 text-sm"><input type="checkbox" className="size-4 accent-blue-500" checked={checked} onChange={(event) => onChange(event.target.checked)} />{label}</label>;
}
