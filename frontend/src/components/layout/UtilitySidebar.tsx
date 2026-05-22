import { useEffect, useRef, useState } from "react";
import { NavLink } from "react-router-dom";
import { ChevronDown, ListChecks, LogOut, User as UserIcon } from "lucide-react";
import clsx from "clsx";
import type { UserPayload } from "@/api/types";
import { AlertsPanel, useAlertsUnread } from "@/components/layout/HeaderAlerts";

export const UTILITY_NAV = [
  { to: "/watchlist", label: "Watchlist", icon: ListChecks },
] as const;

type UtilityMenuProps = {
  user: UserPayload | null;
  onSignOut: () => void;
  open: boolean;
  onClose: () => void;
};

export function UtilityMenuToggle({
  onOpen,
  user,
}: {
  onOpen: () => void;
  user: UserPayload | null;
}) {
  const unread = useAlertsUnread();

  return (
    <button
      type="button"
      onClick={onOpen}
      aria-label="Open account menu"
      aria-haspopup="dialog"
      className="relative inline-flex items-center justify-center size-9 rounded-xl text-ink-mute hover:text-ink hover:bg-surface transition-colors shrink-0"
    >
      <div className="size-8 rounded-full bg-surface-2 border border-line flex items-center justify-center">
        <UserIcon size={16} />
      </div>
      {unread > 0 && (
        <span className="absolute top-0.5 right-0.5 min-w-[14px] h-[14px] px-0.5 rounded-full bg-negative text-[9px] font-semibold text-white flex items-center justify-center leading-none">
          {unread > 9 ? "9+" : unread}
        </span>
      )}
      <span className="sr-only">{user?.full_name || user?.email || "Account"}</span>
    </button>
  );
}

/** Account menu (header dropdown) — not a layout sidebar. */
export function UtilityMenu({ user, onSignOut, open, onClose }: UtilityMenuProps) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) onClose();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open, onClose]);

  useEffect(() => {
    if (!open) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      ref={ref}
      role="dialog"
      aria-label="Account menu"
      className="fixed top-14 right-4 md:right-6 lg:right-8 z-40 w-[min(calc(100vw-2rem),18rem)] card shadow-card overflow-x-hidden"
    >
      <UtilityMenuPanel user={user} onSignOut={onSignOut} onNavigate={onClose} defaultMenuOpen />
    </div>
  );
}

function UtilityMenuPanel({
  user,
  onSignOut,
  onNavigate,
  defaultMenuOpen = true,
}: {
  user: UserPayload | null;
  onSignOut: () => void;
  onNavigate?: () => void;
  defaultMenuOpen?: boolean;
}) {
  const [menuOpen, setMenuOpen] = useState(defaultMenuOpen);

  const handleSignOut = () => {
    onNavigate?.();
    onSignOut();
  };

  return (
    <div className="flex flex-col min-w-0 p-4 overflow-x-hidden">
      <button
        type="button"
        onClick={() => setMenuOpen((open) => !open)}
        aria-expanded={menuOpen}
        aria-label="Account menu"
        className={clsx(
          "flex items-center gap-3 rounded-xl text-left transition-colors shrink-0 w-full px-2 py-2 hover:bg-surface/70",
          menuOpen && "bg-surface/50",
        )}
      >
        <div className="size-9 rounded-full bg-surface-2 border border-line flex items-center justify-center shrink-0">
          <UserIcon size={16} />
        </div>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-medium truncate">{user?.full_name || user?.email}</div>
          <div className="text-xs text-ink-soft truncate">{user?.email}</div>
        </div>
        <ChevronDown
          size={16}
          className={clsx(
            "shrink-0 text-ink-soft transition-transform duration-200",
            menuOpen && "rotate-180",
          )}
        />
      </button>

      {menuOpen && (
        <div className="flex flex-col mt-3 pt-3 border-t border-line/60 min-w-0">
          <nav className="flex flex-col gap-1 shrink-0 w-full min-w-0">
            {UTILITY_NAV.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                onClick={onNavigate}
                className={({ isActive }) =>
                  clsx(
                    "flex items-center gap-3 px-3 py-2 rounded-xl text-sm transition-colors w-full",
                    isActive
                      ? "bg-surface text-ink border border-line"
                      : "text-ink-mute hover:text-ink hover:bg-surface/70",
                  )
                }
              >
                <item.icon size={18} className="shrink-0" />
                <span>{item.label}</span>
              </NavLink>
            ))}
          </nav>

          <div className="mt-4 flex flex-col border-t border-line/60 pt-4 min-w-0">
            <AlertsPanel variant="sidebar" compact onNavigate={onNavigate} />
          </div>

          <div className="mt-4 pt-4 border-t border-line/60 shrink-0">
            <button
              onClick={handleSignOut}
              className="btn-ghost w-full justify-start gap-2 text-sm"
            >
              <LogOut size={16} />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/** @deprecated Use UtilityMenu + UtilityMenuToggle */
export const UtilitySidebar = UtilityMenu;
/** @deprecated Use UtilityMenuToggle */
export const UtilitySidebarToggle = UtilityMenuToggle;
