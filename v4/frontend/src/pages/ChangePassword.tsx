import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { KeyRound } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { User } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { Spinner } from "@/components/common/Spinner";

export function ChangePassword() {
  const { user, setUser } = useAuth();
  const navigate = useNavigate();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => api<User>("/auth/change-password", { method: "POST", body: { current_password: currentPassword, new_password: newPassword } }),
    onSuccess: (current) => { setUser(current); navigate("/", { replace: true }); },
  });

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (newPassword.length < 12) { setLocalError("The new password must contain at least 12 characters."); return; }
    if (newPassword !== confirmPassword) { setLocalError("The new passwords do not match."); return; }
    setLocalError(null);
    mutation.mutate();
  };

  return (
    <main className="min-h-screen grid place-items-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-7 text-center"><div className="mx-auto grid size-12 place-items-center rounded-2xl border border-brand/25 bg-brand/10 text-brand-soft"><KeyRound size={22} /></div><h1 className="mt-4 text-2xl font-semibold">Change password</h1><p className="mt-2 text-sm text-ink-mute">{user?.must_change_password ? "Replace your temporary password before continuing." : "Update the password for your account."}</p></div>
        <form className="card space-y-4 p-6" onSubmit={submit}>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Current password</span><input className="input" type="password" autoComplete="current-password" required value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} /></label>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">New password</span><input className="input" type="password" autoComplete="new-password" minLength={12} required value={newPassword} onChange={(event) => setNewPassword(event.target.value)} /><span className="mt-1 block text-[11px] text-ink-soft">At least 12 characters.</span></label>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Confirm new password</span><input className="input" type="password" autoComplete="new-password" minLength={12} required value={confirmPassword} onChange={(event) => setConfirmPassword(event.target.value)} /></label>
          {(localError || mutation.isError) && <p className="text-sm text-negative" role="alert">{localError || (mutation.error as Error).message}</p>}
          <div className="flex justify-end gap-2">{!user?.must_change_password && <button type="button" className="btn-secondary" onClick={() => navigate(-1)}>Cancel</button>}<button className="btn-primary" type="submit" disabled={mutation.isPending}>{mutation.isPending && <Spinner />}Save password</button></div>
        </form>
      </div>
    </main>
  );
}
