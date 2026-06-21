import { useState } from "react";
import { Outlet, NavLink, useNavigate, useLocation } from "react-router-dom";
import {
  LayoutDashboard,
  Building2,
  Activity,
  Search,
  ShieldAlert,
  Upload,
} from "lucide-react";
import clsx from "clsx";
import { useAuthStore } from "@/store/auth";
import { TopSearch } from "@/components/layout/TopSearch";
import { UtilityMenu, UtilityMenuToggle } from "@/components/layout/UtilitySidebar";

const NAV = [
  { to: "/", label: "Feed", icon: LayoutDashboard, end: true },
  { to: "/companies", label: "Companies", icon: Building2 },
  { to: "/signals", label: "Signals", icon: Activity },
  { to: "/search", label: "Search", icon: Search },
];

const ADMIN_NAV = [
  { to: "/admin/ingest", label: "Ingest", icon: Upload, showOnMobile: false },
  { to: "/admin/review", label: "Review Queue", mobileLabel: "Review", icon: ShieldAlert },
];

export function AppShell() {
  const navigate = useNavigate();
  const location = useLocation();
  const { user, logout } = useAuthStore();
  const [utilityOpen, setUtilityOpen] = useState(false);

  const signOut = () => {
    logout();
    navigate("/login");
  };

  return (
    <div className="min-h-screen flex">
      {/* Left sidebar (desktop) */}
      <aside className="hidden lg:flex w-60 xl:w-64 shrink-0 border-r border-line/70 bg-bg-deep/40 backdrop-blur sticky top-0 h-screen flex-col px-4 py-5">
        <button
          onClick={() => navigate("/")}
          className="flex items-center gap-2 px-2 mb-6"
        >
          <Logo />
          <span className="text-base font-semibold tracking-tight">CapitalNerve</span>
        </button>

        <nav className="flex flex-col gap-1">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                clsx(
                  "flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-colors",
                  isActive
                    ? "bg-surface text-ink border border-line"
                    : "text-ink-mute hover:text-ink hover:bg-surface/70",
                )
              }
            >
              <item.icon size={18} />
              {item.label}
            </NavLink>
          ))}
          {user?.user_type === "ADMIN" &&
            ADMIN_NAV.map((item, index) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-colors",
                    index === 0 && "mt-2",
                    isActive
                      ? "bg-surface text-ink border border-line"
                      : "text-ink-mute hover:text-ink hover:bg-surface/70",
                  )
                }
              >
                <item.icon size={18} />
                {item.label}
              </NavLink>
            ))}
        </nav>
      </aside>

      {/* Main column */}
      <main className="flex-1 min-w-0 flex flex-col">
        <header className="sticky top-0 z-30 border-b border-line/70 bg-bg/80 backdrop-blur">
          <div className="flex items-center gap-2 sm:gap-3 px-4 md:px-6 lg:px-8 h-14 min-w-0">
            <button
              onClick={() => navigate("/")}
              className="lg:hidden flex items-center gap-2 shrink-0"
              aria-label="Home"
            >
              <Logo small />
              <span className="hidden sm:inline text-sm font-semibold">CapitalNerve</span>
            </button>
            <div className="flex-1 min-w-0 max-w-2xl mx-auto">
              <TopSearch />
            </div>
            <UtilityMenuToggle user={user} onOpen={() => setUtilityOpen(true)} />
          </div>
        </header>

        <UtilityMenu
          user={user}
          onSignOut={signOut}
          open={utilityOpen}
          onClose={() => setUtilityOpen(false)}
        />

        <div className="flex-1 px-4 md:px-6 lg:px-8 py-4 md:py-6 pb-24 lg:pb-8">
          <Outlet />
        </div>
      </main>

      {/* Mobile bottom nav */}
      <nav className="lg:hidden fixed bottom-0 inset-x-0 z-40 bg-bg-deep/95 backdrop-blur border-t border-line/70">
        <div className="flex items-center justify-around px-1 py-2 pb-[max(env(safe-area-inset-bottom),0.5rem)]">
          {NAV.map((item) => {
            const active =
              item.end ? location.pathname === item.to : location.pathname.startsWith(item.to);
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                className={clsx(
                  "flex flex-col items-center gap-0.5 px-1.5 py-1.5 rounded-lg text-[10px] sm:text-[11px] flex-1 min-w-0 max-w-[4.5rem]",
                  active ? "text-ink" : "text-ink-soft",
                )}
              >
                <item.icon size={20} className="shrink-0" />
                <span className="truncate w-full text-center">{item.label}</span>
              </NavLink>
            );
          })}
          {user?.user_type === "ADMIN" &&
            ADMIN_NAV.filter((item) => item.showOnMobile !== false).map((item) => {
              const active = location.pathname.startsWith(item.to);
              return (
                <NavLink
                  key={item.to}
                  to={item.to}
                  className={clsx(
                    "flex flex-col items-center gap-0.5 px-1.5 py-1.5 rounded-lg text-[10px] sm:text-[11px] flex-1 min-w-0 max-w-[4.5rem]",
                    active ? "text-ink" : "text-ink-soft",
                  )}
                >
                  <item.icon size={20} className="shrink-0" />
                  <span className="truncate w-full text-center">
                    {item.mobileLabel ?? item.label}
                  </span>
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
