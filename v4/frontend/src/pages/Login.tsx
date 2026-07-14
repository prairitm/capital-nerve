import { useState } from "react";
import { Navigate, useLocation, useNavigate } from "react-router-dom";
import { ArrowRight, ShieldCheck } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { useAuth } from "@/auth/AuthContext";
import { Spinner } from "@/components/common/Spinner";

export function Login() {
  const { user, loading, login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const mutation = useMutation({
    mutationFn: () => login(email, password),
    onSuccess: (current) => {
      navigate(
        current.must_change_password ? "/change-password" : location.state?.from || "/",
        { replace: true },
      );
    },
  });

  if (!loading && user) {
    return <Navigate to={user.must_change_password ? "/change-password" : "/"} replace />;
  }

  return (
    <main className="min-h-screen grid place-items-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-7 text-center">
          <div className="mx-auto grid size-12 place-items-center rounded-2xl border border-brand/25 bg-brand/10 text-brand-soft"><ShieldCheck size={23} /></div>
          <h1 className="mt-4 text-3xl font-semibold tracking-tight">Welcome to CapitalNerve</h1>
          <p className="mt-2 text-sm text-ink-mute">Sign in to your company intelligence workspace.</p>
        </div>
        <form className="card space-y-4 p-6" onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Email</span><input className="input" type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} /></label>
          <label className="block"><span className="mb-1.5 block text-xs font-medium text-ink-mute">Password</span><input className="input" type="password" autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} /></label>
          {mutation.isError && <p className="text-sm text-negative" role="alert">{(mutation.error as Error).message}</p>}
          <button className="btn-primary w-full" type="submit" disabled={mutation.isPending}>{mutation.isPending && <Spinner />}Sign in <ArrowRight size={16} /></button>
          <p className="text-center text-xs text-ink-soft">Accounts are provisioned by an administrator.</p>
        </form>
      </div>
    </main>
  );
}
