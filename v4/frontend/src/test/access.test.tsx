import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { AuthProvider } from "@/auth/AuthContext";
import { WatchlistButton } from "@/components/company/WatchlistButton";
import { NseCompanyResult } from "@/components/company/NseCompanyResult";
import type { User } from "@/api/types";

vi.mock("@/pages/DocumentPage", () => ({ DocumentPage: () => null }));

const baseUser: User = {
  id: "user-1",
  email: "member@example.com",
  full_name: "Member User",
  role: "MEMBER",
  is_active: true,
  must_change_password: false,
  created_at: "2026-07-14T00:00:00+00:00",
  updated_at: "2026-07-14T00:00:00+00:00",
  last_login_at: null,
};

function json(data: unknown, status = 200) {
  return new Response(status === 204 ? null : JSON.stringify(data), {
    status,
    headers: status === 204 ? undefined : { "Content-Type": "application/json" },
  });
}

function renderApp(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider><MemoryRouter initialEntries={[path]} future={{ v7_startTransition: true, v7_relativeSplatPath: true }}><App /></MemoryRouter></AuthProvider>
    </QueryClientProvider>,
  );
}

describe("role-aware access", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("redirects a temporary-password user to password change", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ ...baseUser, must_change_password: true })));
    renderApp("/companies");
    expect(await screen.findByRole("heading", { name: "Change password" })).toBeInTheDocument();
    expect(screen.getByText("Replace your temporary password before continuing.")).toBeInTheDocument();
  });

  it("shows an admin a generated credential once after creating a user", async () => {
    const admin = { ...baseUser, id: "admin-1", email: "admin@example.com", role: "ADMIN" as const };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/me")) return json(admin);
      if (url.includes("/admin/users") && init?.method === "POST") {
        return json({ user: { ...baseUser, id: "new-user", email: "new@example.com", must_change_password: true }, temporary_password: "temporary-password-1234" }, 201);
      }
      if (url.includes("/admin/users")) return json([]);
      return json({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/admin/users");
    expect(await screen.findByRole("heading", { name: "Users and access" })).toBeInTheDocument();
    fireEvent.change(screen.getByPlaceholderText("Full name"), { target: { value: "New User" } });
    fireEvent.change(screen.getByPlaceholderText("Email address"), { target: { value: "new@example.com" } });
    fireEvent.click(screen.getByRole("button", { name: "Create" }));
    expect(await screen.findByText("temporary-password-1234")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Done" }));
    expect(screen.queryByText("temporary-password-1234")).not.toBeInTheDocument();
  });

  it("sends an idempotent watchlist mutation and refreshes related data", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => json({ watchlist_status: true, added: true }));
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    render(<QueryClientProvider client={queryClient}><WatchlistButton companyId="alpha-id" watched={false} /></QueryClientProvider>);
    fireEvent.click(screen.getByRole("button", { name: "Add to watchlist" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    const [, options] = fetchMock.mock.calls[0];
    expect(options?.method).toBe("PUT");
    expect(String(fetchMock.mock.calls[0][0])).toContain("/watchlist/companies/alpha-id");
  });

  it("starts monitoring an NSE directory result by symbol", async () => {
    const fetchMock = vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) =>
      json({ watchlist_status: true, added: true }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    render(
      <QueryClientProvider client={queryClient}>
        <NseCompanyResult result={{
          symbol: "TATAMOTORS",
          name: "Tata Motors Limited",
          company_name: "Tata Motors Limited",
          series: "EQ",
          listing_date: "22-JUL-1998",
          isin: "INE155A01022",
          company_id: null,
          coverage_status: "available",
        }} />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start monitoring" }));
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    expect(String(fetchMock.mock.calls[0][0])).toContain("/watchlist/companies/by-symbol/TATAMOTORS");
    expect(fetchMock.mock.calls[0][1]?.method).toBe("PUT");
  });

  it("keeps the company search focused while results refresh", async () => {
    const neverResolves = new Promise<Response>(() => undefined);
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/auth/me")) return json(baseUser);
      if (url.includes("/api/companies?search=ta")) return neverResolves;
      if (url.includes("/nse-companies/search")) return json([]);
      if (url.includes("/api/companies")) return json([]);
      return json({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/companies");
    const input = await screen.findByPlaceholderText("Search company or ticker");
    input.focus();
    fireEvent.change(input, { target: { value: "ta" } });
    await waitFor(
      () => expect(fetchMock.mock.calls.some(([url]) => String(url).includes("/api/companies?search=ta"))).toBe(true),
      { timeout: 1000 },
    );
    expect(input).toHaveFocus();
  });

  it("loads and saves watchlist email preferences from Profile", async () => {
    const profile = {
      full_name: "Member User",
      login_email: "member@example.com",
      notification_email: "member@example.com",
      email_enabled: false,
      email_verified: true,
      verification_required: false,
      financial_results_enabled: true,
      investor_presentations_enabled: true,
      earnings_calls_enabled: true,
    };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/auth/me")) return json(baseUser);
      if (url.includes("/api/profile") && init?.method === "PATCH") {
        return json({ ...profile, email_enabled: true });
      }
      if (url.includes("/api/profile")) return json(profile);
      return json({ detail: "Not found" }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp("/profile");
    expect(await screen.findByRole("heading", { name: "Profile and email alerts" })).toBeInTheDocument();
    fireEvent.click(screen.getByLabelText("Enabled"));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));
    await waitFor(() => expect(fetchMock.mock.calls.some(([, options]) => options?.method === "PATCH")).toBe(true));
    const patchCall = fetchMock.mock.calls.find(([, options]) => options?.method === "PATCH");
    expect(JSON.parse(String(patchCall?.[1]?.body)).email_enabled).toBe(true);
    expect(await screen.findByText("Profile saved.")).toBeInTheDocument();
  });

  it("shows a public notification result without requiring login", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => json({ detail: "Not authenticated" }, 401)));
    renderApp("/notifications/verified");
    expect(await screen.findByRole("heading", { name: "Email verified" })).toBeInTheDocument();
  });
});
