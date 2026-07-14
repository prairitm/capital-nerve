import { Link } from "react-router-dom";
import { Activity, ArrowUpRight, CalendarDays } from "lucide-react";
import type { CompanyListItem, SeverityLevel } from "@/api/types";
import { SeverityBadge } from "@/components/common/SeverityBadge";
import { WatchlistButton } from "@/components/company/WatchlistButton";
import { formatDate } from "@/lib/format";

export function CompanyCard({ company }: { company: CompanyListItem }) {
  const ticker = company.ticker ?? company.id;
  const initials = (company.ticker || company.name || "CN").slice(0, 3).toUpperCase();
  return (
    <article className="card flex min-w-0 items-start gap-4 p-4 transition-colors hover:border-line-strong hover:bg-surface-2/55">
      <Link to={`/company/${ticker}`} className="focus-ring grid size-11 shrink-0 place-items-center rounded-xl border border-brand/20 bg-brand/10 text-xs font-bold tracking-wide text-brand-soft" aria-label={`Open ${company.name ?? ticker}`}>{initials}</Link>
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-start justify-between gap-3">
          <Link to={`/company/${ticker}`} className="focus-ring group min-w-0 rounded-lg">
            <h2 className="truncate text-sm font-semibold text-ink group-hover:text-brand-soft">{company.name}</h2>
            <p className="mt-0.5 truncate text-xs text-ink-mute">{company.ticker}{company.industry ? ` · ${company.industry}` : ""}</p>
          </Link>
          <div className="flex shrink-0 items-center gap-1"><WatchlistButton companyId={company.id} watched={company.watchlist_status} compact /><Link to={`/company/${ticker}`} className="focus-ring grid size-9 place-items-center rounded-xl text-ink-soft hover:text-brand-soft" aria-label={`Open ${company.name ?? ticker}`}><ArrowUpRight size={16} /></Link></div>
        </div>
        <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-ink-mute">
          <span className="inline-flex items-center gap-1.5"><CalendarDays size={13} />{company.latest_period_label ?? formatDate(company.latest_event_date)}</span>
          <span className="inline-flex items-center gap-1.5"><Activity size={13} />{company.signal_count} {company.signal_count === 1 ? "signal" : "signals"}</span>
          {company.highest_severity && <SeverityBadge level={company.highest_severity as SeverityLevel} />}
        </div>
      </div>
    </article>
  );
}
