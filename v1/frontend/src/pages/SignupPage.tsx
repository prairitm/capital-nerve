import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { api } from "@/api/client";
import { useAuthStore } from "@/store/auth";
import type { TokenResponse } from "@/api/types";
import { Spinner } from "@/components/common/Spinner";

export function SignupPage() {
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fullName, setFullName] = useState("");

  const m = useMutation({
    mutationFn: async () => {
      return api<TokenResponse>("/auth/signup", {
        method: "POST",
        body: { email, password, full_name: fullName },
      });
    },
    onSuccess: (resp) => {
      setAuth(resp);
      navigate("/");
    },
  });

  return (
    <div className="min-h-screen flex flex-col items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold tracking-tight">Create your account</h1>
          <p className="text-sm text-ink-mute mt-2">Two minutes to your first intelligence feed.</p>
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            m.mutate();
          }}
          className="card p-6 space-y-4"
        >
          <div>
            <label className="text-xs text-ink-mute mb-1 block">Full name</label>
            <input
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              className="input"
              placeholder="Your name"
            />
          </div>
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
              minLength={6}
              required
              className="input"
            />
          </div>
          <button type="submit" disabled={m.isPending} className="btn-primary w-full">
            {m.isPending ? <Spinner /> : null}
            Create account
            <ArrowRight size={16} />
          </button>
          {m.isError && (
            <p className="text-sm text-negative">
              {(m.error as Error).message || "Sign-up failed."}
            </p>
          )}
        </form>
        <div className="mt-4 text-center text-sm text-ink-mute">
          Already have an account?{" "}
          <Link to="/login" className="ui-link">
            Sign in
          </Link>
        </div>
      </div>
    </div>
  );
}
