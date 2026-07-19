import { Outlet, NavLink, useNavigate, useLocation, Link } from "react-router-dom";
import { LayoutDashboard, Building2, Activity, Database, Heart, Users, KeyRound, LogOut, UserRound } from "lucide-react";
import clsx from "clsx";
import { useAuth } from "@/auth/AuthContext";

const NAV = [
  { to: "/", label: "Feed", icon: LayoutDashboard, end: true },
  { to: "/watchlist", label: "Watchlist", icon: Heart },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/signals", label: "Signals", icon: Activity },
];

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuth();
  const nav = user?.role === "ADMIN" ? [...NAV, { to: "/admin/users", label: "Users", icon: Users }] : NAV;
  const signOut = async () => { await logout(); navigate("/login", { replace: true }); };

  return (
    <div className="min-h-screen flex">
      {/* Left sidebar (desktop) */}
      <aside className="hidden lg:flex w-56 shrink-0 border-r border-line/70 bg-bg-deep/80 sticky top-0 h-screen flex-col px-3 py-5">
        <button
          onClick={() => navigate("/")}
          className="focus-ring flex items-center gap-2 rounded-lg px-2 mb-7"
        >
          <Logo />
          <span className="text-base font-semibold tracking-tight">CapitalNerve</span>
        </button>

        <nav className="flex flex-col gap-1">
          {nav.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  "focus-ring flex items-center gap-3 px-3 py-2.5 rounded-xl text-sm font-medium transition-colors",
                  isActive
                    ? "bg-surface-2 text-ink border border-line shadow-sm"
                    : "text-ink-mute hover:text-ink hover:bg-surface/70",
                )
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="mt-auto mx-2 rounded-xl border border-line/60 bg-surface/50 p-3">
          <div className="flex items-center gap-2 text-xs font-medium text-ink-mute"><Database size={14} className="text-positive" />Research data</div>
          <div className="mt-1 text-[11px] text-ink-soft">Company intelligence workspace</div>
        </div>
        <div className="mx-2 mt-3 rounded-xl border border-line/60 bg-surface/50 p-3">
          <Link to="/profile" className="focus-ring block truncate rounded text-xs font-medium text-ink hover:text-brand-soft">{user?.full_name || user?.email}</Link>
          <div className="mt-0.5 flex items-center justify-between gap-2"><span className="truncate text-[11px] text-ink-soft">{user?.role === "ADMIN" ? "Administrator" : "Member"}</span><div className="flex"><Link to="/change-password" className="focus-ring grid size-7 place-items-center rounded-lg text-ink-soft hover:bg-surface-2 hover:text-ink" title="Change password"><KeyRound size={14} /></Link><button type="button" onClick={() => void signOut()} className="focus-ring grid size-7 place-items-center rounded-lg text-ink-soft hover:bg-surface-2 hover:text-ink" title="Sign out"><LogOut size={14} /></button></div></div>
        </div>
      </aside>

      {/* Main column */}
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/80 backdrop-blur lg:hidden">
          <div className="flex items-center gap-2 px-4 h-14 min-w-0">
            <button
              onClick={() => navigate("/")}
              className="flex items-center gap-2 shrink-0"
              aria-label="Home"
            >
              <Logo small />
              <span className="text-sm font-semibold">CapitalNerve</span>
            </button>
            <div className="ml-auto flex items-center gap-1"><Link to="/profile" className="focus-ring grid size-9 place-items-center rounded-xl text-ink-mute hover:bg-surface" aria-label="Profile"><UserRound size={17} /></Link><Link to="/change-password" className="focus-ring grid size-9 place-items-center rounded-xl text-ink-mute hover:bg-surface" aria-label="Change password"><KeyRound size={17} /></Link><button type="button" onClick={() => void signOut()} className="focus-ring grid size-9 place-items-center rounded-xl text-ink-mute hover:bg-surface" aria-label="Sign out"><LogOut size={17} /></button></div>
          </div>
        </header>

        <div className="flex-1 min-w-0 px-4 md:px-6 lg:px-8 xl:px-10 py-5 md:py-7 pb-24 lg:pb-10">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-bg-deep/95 backdrop-blur border-t border-line/70">
        <div className="flex items-center justify-around px-1 py-2 pb-[max(env(safe-area-inset-bottom),0.5rem)]">
          {nav.map((item) => {
            const active = item.end
              ? location.pathname === item.to
              : location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={clsx(
                  "focus-ring flex flex-col items-center gap-0.5 px-1.5 py-1.5 rounded-lg text-[11px] flex-1 min-w-0 max-w-[5rem]",
                  active ? "text-ink" : "text-ink-soft",
                )}
              >
                <item.icon size={20} className="shrink-0" />
                <span className="truncate w-full text-center">{item.label}</span>
              </NavLink>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function Logo({ small = false }: { small?: boolean }) {
  const size = small ? 24 : 28;
  return (
    <svg width={size} height={size} viewBox="0 0 32 32" fill="none" aria-hidden>
      <defs>
        <linearGradient id="cn-g" x1="0" x2="1" y1="0" y2="1">
          <stop offset="0" stopColor="#60A5FA" />
          <stop offset="1" stopColor="#3B82F6" />
        </linearGradient>
      </defs>
      <rect width="32" height="32" rx="8" fill="#141A26" />
      <path
        d="M6 22 L12 12 L17 18 L21 10 L26 22"
        stroke="url(#cn-g)"
        strokeWidth="2.5"
        fill="none"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="26" cy="10" r="2.2" fill="#60A5FA" />
    </svg>
  );
}
