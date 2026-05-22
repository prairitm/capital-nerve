import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { UserPayload, TokenResponse } from "@/api/types";
import { setToken } from "@/api/client";

interface AuthState {
  user: UserPayload | null;
  token: string | null;
  setAuth: (resp: TokenResponse) => void;
  setUser: (user: UserPayload | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      user: null,
      token: null,
      setAuth: (resp: TokenResponse) => {
        setToken(resp.access_token);
        set({
          token: resp.access_token,
          user: {
            user_id: resp.user_id,
            email: resp.email,
            full_name: resp.full_name,
            user_type: resp.user_type,
          },
        });
      },
      setUser: (user) => set({ user }),
      logout: () => {
        setToken(null);
        set({ user: null, token: null });
      },
    }),
    { name: "cn_auth" },
  ),
);
