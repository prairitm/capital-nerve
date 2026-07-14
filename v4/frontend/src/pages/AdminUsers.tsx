import { useEffect, useState } from "react";
import { Copy, KeyRound, Plus, Search, ShieldCheck, UserCheck, UserX, X } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";
import type { TemporaryCredentialResponse, User, UserRole } from "@/api/types";
import { useAuth } from "@/auth/AuthContext";
import { ErrorState, PageHeader, PageSkeleton } from "@/components/common/DashboardUI";
import { Spinner } from "@/components/common/Spinner";
import { formatDate } from "@/lib/format";

export function AdminUsers() {
  const { user: currentUser, refresh } = useAuth();
  const queryClient = useQueryClient();
  const [search, setSearch] = useState("");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<UserRole>("MEMBER");
  const [credential, setCredential] = useState<TemporaryCredentialResponse | null>(null);
  const usersQuery = useQuery({ queryKey: ["admin-users", search], queryFn: () => api<User[]>("/admin/users", { query: { search, limit: 200 } }) });
  const createMutation = useMutation({
    mutationFn: () => api<TemporaryCredentialResponse>("/admin/users", { method: "POST", body: { email, full_name: name || null, role } }),
    onSuccess: (result) => { setCredential(result); setName(""); setEmail(""); setRole("MEMBER"); void queryClient.invalidateQueries({ queryKey: ["admin-users"] }); },
  });

  if (usersQuery.isLoading) return <PageSkeleton rows={5} />;
  if (usersQuery.isError) return <ErrorState title="Unable to load users" description={(usersQuery.error as Error).message} onRetry={() => void usersQuery.refetch()} />;

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader eyebrow="Administration" title="Users and access" description="Provision accounts, assign roles, and control access to the research workspace." action={<span className="chip-neutral"><ShieldCheck size={12} />{usersQuery.data?.filter((user) => user.is_active).length ?? 0} active</span>} />
      <section className="card p-4 md:p-5">
        <div className="mb-4"><h2 className="text-sm font-semibold">Create user</h2><p className="mt-1 text-xs text-ink-mute">A temporary password is generated and shown once.</p></div>
        <form className="grid gap-3 md:grid-cols-[1fr_1.25fr_10rem_auto]" onSubmit={(event) => { event.preventDefault(); createMutation.mutate(); }}>
          <input className="input" placeholder="Full name" maxLength={160} value={name} onChange={(event) => setName(event.target.value)} />
          <input className="input" type="email" placeholder="Email address" required value={email} onChange={(event) => setEmail(event.target.value)} />
          <select className="input" value={role} onChange={(event) => setRole(event.target.value as UserRole)}><option value="MEMBER">Member</option><option value="ADMIN">Admin</option></select>
          <button type="submit" className="btn-primary" disabled={createMutation.isPending}>{createMutation.isPending ? <Spinner /> : <Plus size={16} />}Create</button>
        </form>
        {createMutation.isError && <p className="mt-3 text-sm text-negative" role="alert">{(createMutation.error as Error).message}</p>}
      </section>
      <section className="space-y-3">
        <label className="relative block max-w-md"><span className="sr-only">Search users</span><Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" /><input className="input pl-9" placeholder="Search by name or email" value={search} onChange={(event) => setSearch(event.target.value)} /></label>
        {(usersQuery.data ?? []).map((user) => <UserRow key={user.id} user={user} currentUserId={currentUser?.id ?? ""} onCredential={setCredential} onSelfUpdated={() => void refresh()} />)}
      </section>
      {credential && <CredentialDialog credential={credential} onClose={() => setCredential(null)} />}
    </div>
  );
}

function UserRow({ user, currentUserId, onCredential, onSelfUpdated }: { user: User; currentUserId: string; onCredential: (credential: TemporaryCredentialResponse) => void; onSelfUpdated: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(user.full_name ?? "");
  const [email, setEmail] = useState(user.email);
  const [role, setRole] = useState<UserRole>(user.role);
  useEffect(() => { setName(user.full_name ?? ""); setEmail(user.email); setRole(user.role); }, [user]);
  const update = useMutation({
    mutationFn: (body: Record<string, unknown>) => api<User>(`/admin/users/${user.id}`, { method: "PATCH", body }),
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["admin-users"] }); if (isSelf) onSelfUpdated(); },
  });
  const reset = useMutation({
    mutationFn: () => api<TemporaryCredentialResponse>(`/admin/users/${user.id}/reset-password`, { method: "POST" }),
    onSuccess: (result) => { onCredential(result); void queryClient.invalidateQueries({ queryKey: ["admin-users"] }); },
  });
  const isSelf = user.id === currentUserId;
  const dirty = name.trim() !== (user.full_name ?? "") || email.trim().toLowerCase() !== user.email || role !== user.role;
  const error = update.error || reset.error;
  return (
    <article className={`card p-4 ${user.is_active ? "" : "opacity-70"}`}>
      <div className="grid items-end gap-3 lg:grid-cols-[1fr_1.25fr_10rem_auto]">
        <label><span className="mb-1 block text-[11px] text-ink-soft">Full name</span><input className="input" value={name} maxLength={160} onChange={(event) => setName(event.target.value)} /></label>
        <label><span className="mb-1 block text-[11px] text-ink-soft">Email</span><input className="input" type="email" value={email} onChange={(event) => setEmail(event.target.value)} /></label>
        <label><span className="mb-1 block text-[11px] text-ink-soft">Role</span><select className="input" value={role} disabled={isSelf} onChange={(event) => setRole(event.target.value as UserRole)}><option value="MEMBER">Member</option><option value="ADMIN">Admin</option></select></label>
        <button className="btn-primary" disabled={!dirty || update.isPending} onClick={() => update.mutate({ full_name: name.trim() || null, email: email.trim(), role })}>{update.isPending && <Spinner />}Save</button>
      </div>
      <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-line/50 pt-3">
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-ink-soft"><span>{user.is_active ? "Active" : "Inactive"}</span><span>Created {formatDate(user.created_at)}</span><span>{user.last_login_at ? `Last login ${formatDate(user.last_login_at)}` : "Never signed in"}</span>{user.must_change_password && <span className="text-mixed">Password change required</span>}</div>
        <div className="flex gap-2"><button className="btn-secondary px-2.5 py-1.5 text-xs" disabled={isSelf || reset.isPending} onClick={() => reset.mutate()}><KeyRound size={14} />Reset password</button><button className="btn-secondary px-2.5 py-1.5 text-xs" disabled={isSelf || update.isPending} onClick={() => update.mutate({ is_active: !user.is_active })}>{user.is_active ? <UserX size={14} /> : <UserCheck size={14} />}{user.is_active ? "Deactivate" : "Reactivate"}</button></div>
      </div>
      {error && <p className="mt-3 text-sm text-negative" role="alert">{(error as Error).message}</p>}
    </article>
  );
}

function CredentialDialog({ credential, onClose }: { credential: TemporaryCredentialResponse; onClose: () => void }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => { await navigator.clipboard.writeText(credential.temporary_password); setCopied(true); };
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-labelledby="credential-title">
      <div className="card w-full max-w-md p-5">
        <div className="flex items-start justify-between gap-3"><div><h2 id="credential-title" className="text-base font-semibold">Temporary password</h2><p className="mt-1 text-xs text-ink-mute">Share this securely with {credential.user.email}. It will not be shown again.</p></div><button className="focus-ring grid size-8 place-items-center rounded-lg text-ink-mute hover:bg-surface-2" onClick={onClose} aria-label="Close"><X size={17} /></button></div>
        <div className="mt-5 rounded-xl border border-line bg-bg-deep p-4 font-mono text-sm break-all text-ink">{credential.temporary_password}</div>
        <div className="mt-4 flex justify-end gap-2"><button className="btn-secondary" onClick={() => void copy()}><Copy size={15} />{copied ? "Copied" : "Copy"}</button><button className="btn-primary" onClick={onClose}>Done</button></div>
      </div>
    </div>
  );
}
