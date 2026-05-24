import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import { MessageSquare, Search } from "lucide-react";
import { api } from "@/api/client";
import type { AskResponse, CompanyBrief, SearchResult } from "@/api/types";
import { documentSourceHref } from "@/components/common/SourceDocumentLink";
import { PageLoader } from "@/components/common/Spinner";
import { SignalBadge } from "@/components/common/SignalBadge";
import { SeverityBadge } from "@/components/common/SeverityBadge";

export function SearchPage() {
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") || "";
  const [q, setQ] = useState(initial);
  const [askQ, setAskQ] = useState("");
  const [companyId, setCompanyId] = useState<number | "">("");

  useEffect(() => {
    setQ(params.get("q") || "");
  }, [params]);

  const { data, isLoading } = useQuery({
    queryKey: ["search", q],
    queryFn: () => api<SearchResult>("/search", { query: { q } }),
    enabled: q.length > 0,
  });

  const { data: companies } = useQuery({
    queryKey: ["companies", "search-picker"],
    queryFn: () => api<CompanyBrief[]>("/v1/companies", { query: { search: "", limit: 200 } }),
  });

  const askMutation = useMutation({
    mutationFn: (body: { q: string; company_id?: number }) =>
      api<AskResponse>("/search/ask", { method: "POST", body }),
  });

  const hasResults =
    !!data &&
    (data.companies.length > 0 ||
      data.cards.length > 0 ||
      data.events.length > 0 ||
      data.document_hits.length > 0);

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Search & Ask</h1>
        <p className="text-sm text-ink-mute">
          Search companies, events, cards, and filing text — or ask a question across indexed documents.
        </p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          setParams({ q });
        }}
        className="relative"
      >
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft" />
        <input
          autoFocus
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder='Try: "order book", "margin compression", or a company name'
          className="input pl-9"
        />
      </form>

      <section className="card p-4 space-y-3">
        <div className="flex items-center gap-2 text-sm font-semibold">
          <MessageSquare size={16} className="text-ink-soft" />
          Ask across filings
        </div>
        <textarea
          value={askQ}
          onChange={(e) => setAskQ(e.target.value)}
          placeholder="What did management say about demand on the last concall?"
          rows={3}
          className="input resize-y min-h-[4.5rem]"
        />
        <div className="flex flex-col sm:flex-row gap-2 sm:items-center">
          <select
            value={companyId}
            onChange={(e) => setCompanyId(e.target.value ? Number(e.target.value) : "")}
            className="input sm:max-w-xs"
          >
            <option value="">All companies</option>
            {(companies ?? []).map((c) => (
              <option key={c.company_id} value={c.company_id}>
                {c.company_name}
              </option>
            ))}
          </select>
          <button
            type="button"
            disabled={askQ.trim().length === 0 || askMutation.isPending}
            onClick={() =>
              askMutation.mutate({
                q: askQ.trim(),
                ...(companyId !== "" ? { company_id: companyId } : {}),
              })
            }
            className="btn-primary sm:ml-auto"
          >
            {askMutation.isPending ? "Asking…" : "Ask"}
          </button>
        </div>
        {askMutation.data && (
          <div className="pt-2 border-t border-line space-y-3">
            <p className="text-sm leading-relaxed whitespace-pre-wrap">{askMutation.data.answer}</p>
            <p className="text-[11px] uppercase tracking-wider text-ink-soft">
              {askMutation.data.retrieval_mode === "hybrid" ? "Hybrid retrieval" : "Keyword retrieval only"}
            </p>
            {askMutation.data.citations.length > 0 && (
              <ul className="space-y-2 text-sm">
                {askMutation.data.citations.map((c) => (
                  <li key={`${c.document_id}-${c.page_id}-${c.quote.slice(0, 24)}`} className="text-ink-mute">
                    <Link
                      to={documentSourceHref(c.document_id, c.page_number)}
                      className="ui-link font-medium text-ink"
                    >
                      Page {c.page_number}
                    </Link>
                    <span className="text-ink-soft"> — </span>
                    <span className="line-clamp-2">{c.quote}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}
        {askMutation.isError && (
          <p className="text-sm text-negative">Could not generate an answer. Try again.</p>
        )}
      </section>

      {q.length === 0 ? (
        <div className="card p-6 text-sm text-ink-mute">
          Examples:
          <ul className="mt-2 space-y-1 list-disc list-inside">
            <li>Route Mobile</li>
            <li>order book</li>
            <li>pricing power</li>
            <li>Margin compression</li>
          </ul>
        </div>
      ) : isLoading || !data ? (
        <PageLoader />
      ) : (
        <div className="space-y-6">
          {data.companies.length > 0 && (
            <Section title="Companies">
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                {data.companies.map((c) => (
                  <Link
                    key={c.company_id}
                    to={`/company/${c.nse_symbol || c.bse_code}`}
                    className="card p-4 hover:border-line-strong block"
                  >
                    <div className="font-semibold">{c.company_name}</div>
                    <div className="text-xs text-ink-soft">
                      {c.nse_symbol} · {c.sector_name}
                    </div>
                  </Link>
                ))}
              </div>
            </Section>
          )}
          {data.document_hits.length > 0 && (
            <Section title="In filings">
              <div className="space-y-2">
                {data.document_hits.map((hit) => (
                  <Link
                    key={`${hit.document_id}-${hit.page_number}-${hit.rank}`}
                    to={documentSourceHref(hit.document_id, hit.page_number)}
                    className="card p-4 hover:border-line-strong block"
                  >
                    <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                      {`${hit.document_type.replace(/_/g, " ")} · p.${hit.page_number}`}
                    </div>
                    <div className="font-medium mt-1">{hit.document_title}</div>
                    <div className="text-xs text-ink-soft mt-0.5">
                      {hit.company_name}
                      {hit.company_symbol ? ` · ${hit.company_symbol}` : ""}
                    </div>
                    <p
                      className="text-sm text-ink-mute mt-2 line-clamp-3"
                      dangerouslySetInnerHTML={{ __html: hit.snippet }}
                    />
                  </Link>
                ))}
              </div>
            </Section>
          )}
          {data.cards.length > 0 && (
            <Section title="Intelligence Cards">
              <div className="grid grid-cols-1 md:grid-cols-2 2xl:grid-cols-3 gap-3">
                {data.cards.map((c) => (
                  <div id={`card-${c.card_id}`} key={c.card_id} className="card rounded-xl p-3">
                    <div className="text-[10px] uppercase tracking-wider text-ink-soft">
                      {c.card_type.replace(/_/g, " ")}
                    </div>
                    <div className="text-sm font-medium mt-0.5 line-clamp-2">{c.headline}</div>
                    <p className="text-xs text-ink-mute mt-1 line-clamp-2">{c.one_line_summary}</p>
                    <div className="mt-1.5 flex items-center gap-1.5">
                      <SignalBadge direction={c.signal_direction} />
                      <SeverityBadge level={c.severity} />
                      <span className="text-[11px] text-ink-soft ml-auto">{c.company_name}</span>
                    </div>
                  </div>
                ))}
              </div>
            </Section>
          )}
          {data.events.length > 0 && (
            <Section title="Events">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {data.events.map((e) => (
                  <Link
                    key={e.event_id}
                    to={`/company/${e.company_symbol}/event/${e.event_id}`}
                    className="card p-4 hover:border-line-strong block"
                  >
                    <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                      {e.event_type.replace(/_/g, " ")}
                    </div>
                    <div className="font-medium mt-1">{e.event_title}</div>
                    <div className="text-xs text-ink-soft mt-1">
                      {e.company_name} · {new Date(e.event_date).toLocaleDateString()}
                    </div>
                  </Link>
                ))}
              </div>
            </Section>
          )}
          {!hasResults && <div className="card p-6 text-sm text-ink-mute text-center">No matches.</div>}
        </div>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section>
      <h2 className="text-base font-semibold mb-3">{title}</h2>
      {children}
    </section>
  );
}
