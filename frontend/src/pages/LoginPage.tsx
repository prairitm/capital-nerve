import { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { ArrowRight, Sparkles } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/store/auth";
import type { TokenResponse } from "@/api/types";
import { Spinner } from "@/components/common/Spinner";

export function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation() as { state?: { from?: string } };
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  const m = useMutation({
    mutationFn: async () => {
      return api<TokenResponse>("/auth/login", {
        method: "POST",
        body: { email, password },
      });
    },
    onSuccess: (resp) => {
      setAuth(resp);
      navigate(location.state?.from || "/", { replace: true });
    },
  });

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <div className="inline-flex items-center gap-2 text-xs text-ink-mute mb-3 px-3 py-1 rounded-full border border-line bg-surface">
            <Sparkles size={12} className="ui-icon" />
            Indian market intelligence
          </div>
          <h1 className="text-3xl font-bold tracking-tight">Welcome to CapitalNerve</h1>
          <p className="text-sm text-ink-mute mt-2">
            Discover signals, not documents. Verify with evidence.
          </p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
          className="card p-6 space-y-4"
        >
          <div>
            <label className="text-xs text-ink-mute mb-1 block">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="input"
            />
          </div>
          <div>
            <label className="text-xs text-ink-mute mb-1 block">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="input"
            />
          </div>
          <button type="submit" disabled={m.isPending} className="btn-primary w-full">
            {m.isPending ? <Spinner /> : null}
            Sign in
            <ArrowRight size={16} />
          </button>
          {m.isError && (
            <p className="text-sm text-negative">
              {(m.error as Error).message || "Sign-in failed."}
            </p>
          )}
        </form>
        <div className="mt-4 text-center text-sm text-ink-mute">
          <p>
            New here?{" "}
            <Link to="/signup" className="ui-link">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
