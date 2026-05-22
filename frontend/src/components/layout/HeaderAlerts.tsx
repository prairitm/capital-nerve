import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Bell } from "lucide-react";
import clsx from "clsx";
import { api } from "@/api/client";
import type { AlertItem } from "@/api/types";
import { relativeDate } from "@/lib/format";

function useAlerts() {
  const { data } = useQuery({
    queryKey: ["alerts"],
    queryFn: () => api<AlertItem[]>("/alerts"),
  });
  const alerts = data ?? [];
  const unread = alerts.filter((a) => !a.is_read).length;
  return { alerts, unread };
}

export function useAlertsUnread() {
  return useAlerts().unread;
}

type AlertsPanelProps = {
  variant: "popover" | "sidebar" | "rail";
  /** When true, alerts list does not use a nested scroll region (e.g. header account menu). */
  compact?: boolean;
  onNavigate?: () => void;
};

export function AlertsPanel({ variant, compact = false, onNavigate }: AlertsPanelProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { alerts, unread } = useAlerts();
  const isPopover = variant === "popover" || variant === "rail";

  useEffect(() => {
    if (!isPopover) return;
    const handler = (e: MouseEvent) => {
      if (!ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isPopover]);

  const openAlert = (a: AlertItem) => {
    setOpen(false);
    onNavigate?.();
    if (a.company_symbol) {
      navigate(`/company/${a.company_symbol}`);
    }
  };

  const list = (
    <>
      {alerts.length === 0 ? (
        <p className="px-3 py-4 text-sm text-ink-mute">No alerts right now.</p>
      ) : (
        <ul className="space-y-0.5">
          {alerts.slice(0, 8).map((a) => (
            <li key={a.alert_id}>
              <button
                type="button"
                onClick={() => openAlert(a)}
                disabled={!a.company_symbol}
                className={clsx(
                  "w-full text-left px-3 py-2.5 rounded-lg transition-colors",
                  a.company_symbol ? "hover:bg-surface-2" : "cursor-default",
                  !a.is_read && "bg-surface-2/40",
                )}
              >
                <div className="text-sm font-medium leading-snug pr-2">{a.alert_title}</div>
                <div className="text-xs text-ink-soft mt-1">
                  {a.company_name && <span>{a.company_name}</span>}
                  {a.company_name && <span className="mx-1.5 text-line">·</span>}
                  <span>{relativeDate(a.created_at)}</span>
                </div>
              </button>
            </li>
          ))}
        </ul>
      )}
    </>
  );

  if (variant === "sidebar") {
    return (
      <div className={clsx("flex flex-col min-w-0", !compact && "min-h-0 flex-1")}>
        <div className="flex items-center gap-2 px-2 py-1.5 shrink-0 min-w-0">
          <Bell size={16} className="text-ink-mute shrink-0" />
          <span className="text-[11px] uppercase tracking-wider text-ink-soft font-medium">Alerts</span>
          {unread > 0 && (
            <span className="ml-auto min-w-[18px] h-[18px] px-1 rounded-full bg-negative text-[10px] font-semibold text-white flex items-center justify-center leading-none shrink-0">
              {unread > 9 ? "9+" : unread}
            </span>
          )}
        </div>
        <div
          className={clsx(
            "min-w-0 px-1",
            compact ? "" : "flex-1 min-h-0 overflow-y-auto -mx-1",
          )}
        >
          {list}
        </div>
      </div>
    );
  }

  return (
    <div ref={ref} className={clsx("relative shrink-0", variant === "rail" && "w-full flex justify-center")}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-label={unread > 0 ? `${unread} unread alerts` : "Alerts"}
        title={variant === "rail" ? "Alerts" : undefined}
        className={clsx(
          "relative inline-flex items-center justify-center size-9 rounded-xl transition-colors",
          open ? "bg-surface-2 text-ink" : "text-ink-mute hover:text-ink hover:bg-surface",
        )}
      >
        <Bell size={18} />
        {unread > 0 && (
          <span className="absolute top-1 right-1 min-w-[14px] h-[14px] px-0.5 rounded-full bg-negative text-[9px] font-semibold text-white flex items-center justify-center leading-none">
            {unread > 9 ? "9+" : unread}
          </span>
        )}
      </button>

      {open && (
        <div
          className={clsx(
            "absolute w-[min(calc(100vw-2rem),20rem)] card p-2 max-h-[min(60vh,24rem)] overflow-y-auto z-40 shadow-card",
            variant === "rail"
              ? "right-full top-0 mr-2"
              : "right-0 top-full mt-2",
          )}
        >
          <div className="px-2 py-1.5 text-[11px] uppercase tracking-wider text-ink-soft font-medium">
            Alerts
          </div>
          {list}
        </div>
      )}
    </div>
  );
}

/** @deprecated Use AlertsPanel in UtilitySidebar */
export function HeaderAlerts() {
  return <AlertsPanel variant="popover" />;
}
