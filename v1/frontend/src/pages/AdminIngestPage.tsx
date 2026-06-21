import { useMemo, useRef, useState } from "react";
import { Navigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Upload,
  RefreshCcw,
  FileText,
  AlertCircle,
  CheckCircle2,
  Clock,
  Loader2,
  Trash2,
  type LucideIcon,
} from "lucide-react";
import clsx from "clsx";
import { api, apiUpload } from "@/api/client";
import type {
  ClearAllCompaniesResponse,
  CompanyBrief,
  CreateCompanyResponse,
  DocumentType,
  EventType,
  ExtractionJobBrief,
  ExtractionStatus,
  IngestUploadResponse,
  SectorBrief,
} from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { useAuthStore } from "@/store/auth";

const EVENT_TYPES: EventType[] = [
  "QUARTERLY_RESULT",
  "CONCALL_TRANSCRIPT",
  "INVESTOR_PRESENTATION",
  "PRESS_RELEASE",
  "EXCHANGE_FILING",
  "SHAREHOLDING_PATTERN",
  "ANNUAL_REPORT",
  "CREDIT_RATING",
];

function jobSignalsCount(job: ExtractionJobBrief): number | null {
  const stages = job.meta?.stages as { signals?: number } | undefined;
  return typeof stages?.signals === "number" ? stages.signals : null;
}

const DOCUMENT_TYPES: DocumentType[] = [
  "FINANCIAL_RESULT",
  "CONCALL_TRANSCRIPT",
  "INVESTOR_PRESENTATION",
  "PRESS_RELEASE",
  "EXCHANGE_FILING",
  "ANNUAL_REPORT",
  "CREDIT_RATING_REPORT",
];

export function AdminIngestPage() {
  const user = useAuthStore((s) => s.user);
  const qc = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);

  const [companyMode, setCompanyMode] = useState<"existing" | "new">("existing");
  const [companyId, setCompanyId] = useState<number | "">("");
  const [newName, setNewName] = useState("");
  const [newShortName, setNewShortName] = useState("");
  const [newSymbol, setNewSymbol] = useState("");
  const [newSector, setNewSector] = useState("");
  const [newIndustry, setNewIndustry] = useState("");
  const [eventType, setEventType] = useState<EventType>("QUARTERLY_RESULT");
  const [documentType, setDocumentType] = useState<DocumentType>("FINANCIAL_RESULT");
  const [periodLabel, setPeriodLabel] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [documentUrl, setDocumentUrl] = useState("");
  const [lastResponse, setLastResponse] = useState<IngestUploadResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [clearMessage, setClearMessage] = useState<string | null>(null);

  const { data: companies, isLoading: companiesLoading } = useQuery({
    queryKey: ["companies", ""],
    queryFn: () => api<CompanyBrief[]>("/v1/companies", { query: { search: "", limit: 200 } }),
    enabled: user?.user_type === "ADMIN",
  });

  const { data: sectors } = useQuery({
    queryKey: ["admin-sectors"],
    queryFn: () => api<SectorBrief[]>("/admin/sectors"),
    enabled: user?.user_type === "ADMIN",
  });

  const createCompany = useMutation({
    mutationFn: () =>
      api<CreateCompanyResponse>("/admin/companies", {
        method: "POST",
        body: {
          company_name: newName.trim(),
          short_name: newShortName.trim() || undefined,
          nse_symbol: newSymbol.trim() || undefined,
          sector_name: newSector.trim() || undefined,
          industry: newIndustry.trim() || undefined,
        },
      }),
    onSuccess: (res) => {
      setCompanyId(res.company.company_id);
      setCompanyMode("existing");
      setErrorMessage(null);
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (err: Error) => setErrorMessage(err.message || "Could not create company"),
  });

  const clearAllCompanies = useMutation({
    mutationFn: () =>
      api<ClearAllCompaniesResponse>("/admin/clear-all-companies", { method: "POST" }),
    onSuccess: (res) => {
      setCompanyId("");
      setLastResponse(null);
      setErrorMessage(null);
      setClearMessage(
        res.companies_removed === 0
          ? "No companies were registered — catalog and users are unchanged."
          : `Removed ${res.companies_removed} ${
              res.companies_removed === 1 ? "company" : "companies"
            }${res.symbols.length ? ` (${res.symbols.join(", ")})` : ""}. Catalog definitions and users are unchanged.`,
      );
      qc.invalidateQueries({ queryKey: ["companies"] });
      qc.invalidateQueries({ queryKey: ["extraction-jobs"] });
      qc.invalidateQueries({ queryKey: ["review"] });
      qc.invalidateQueries({ queryKey: ["watchlist"] });
      qc.invalidateQueries({ queryKey: ["feedSummary"] });
      qc.invalidateQueries({ queryKey: ["feed"] });
    },
  });

  const handleClearAllCompanies = () => {
    const count = companies?.length ?? 0;
    const detail =
      count === 0
        ? "The database has no companies yet. This only confirms the empty state."
        : `This permanently deletes ${count} ${
            count === 1 ? "company" : "companies"
          } and all events, documents, jobs, facts, metrics, signals, cards, evidence, watchlist links, and alerts tied to them.`;
    const ok = window.confirm(
      `Clear all company data?\n\n${detail}\n\nKeeps: metric/signal catalog, financial periods, sectors, and user accounts.\n\nUploaded files may remain on disk under storage — remove manually if needed.`,
    );
    if (!ok) return;
    setClearMessage(null);
    clearAllCompanies.mutate(undefined, {
      onError: (err: Error) => setErrorMessage(err.message || "Could not clear companies"),
    });
  };

  const { data: jobs, isLoading: jobsLoading } = useQuery({
    queryKey: ["extraction-jobs"],
    queryFn: () => api<ExtractionJobBrief[]>("/ingest/jobs", { query: { limit: 30 } }),
    enabled: user?.user_type === "ADMIN",
    refetchInterval: 4000,
  });

  const hasSource = Boolean(file) || documentUrl.trim().length > 0;

  const upload = useMutation({
    mutationFn: async () => {
      const url = documentUrl.trim();
      if (!file && !url) throw new Error("Pick a file or enter a document URL.");
      if (!companyId) throw new Error("Pick or create a company first.");
      const period = periodLabel.trim();
      if (!period) throw new Error("Enter a period label first.");
      const fd = new FormData();
      if (file) fd.append("file", file);
      if (url) fd.append("document_url", url);
      fd.append("company_id", String(companyId));
      fd.append("event_type", eventType);
      fd.append("document_type", documentType);
      fd.append("document_title", period);
      fd.append("period_label", period);
      if (eventDate) fd.append("event_date", eventDate);
      return apiUpload<IngestUploadResponse>("/ingest/upload", fd);
    },
    onSuccess: (res) => {
      setLastResponse(res);
      setErrorMessage(null);
      setFile(null);
      setDocumentUrl("");
      if (fileInput.current) fileInput.current.value = "";
      qc.invalidateQueries({ queryKey: ["extraction-jobs"] });
      qc.invalidateQueries({ queryKey: ["review"] });
    },
    onError: (err: Error) => {
      setErrorMessage(err.message || "Upload failed");
    },
  });

  const selectedCompany = useMemo(
    () => companies?.find((c) => c.company_id === companyId) ?? null,
    [companies, companyId],
  );

  if (user && user.user_type !== "ADMIN") return <Navigate to="/" replace />;
  if (companiesLoading) return <PageLoader />;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-semibold tracking-tight">Ingest documents</h1>
        <p className="text-sm text-ink-mute">
          Upload a PDF or text filing, or paste a direct document URL, for any company — create a
          new issuer first if needed.
          The pipeline builds facts, metrics, signals, and cards.
        </p>
      </div>

      <section className="card border-negative/30 bg-negative-bg/20 p-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-ink">Start fresh</h2>
          <p className="text-xs text-ink-mute mt-1">
            Remove every company and all pipeline intelligence. Catalog definitions (metrics,
            signals, line items) and user accounts stay in place.
          </p>
          {clearMessage && (
            <p className="text-xs text-ink mt-2" role="status">
              {clearMessage}
            </p>
          )}
        </div>
        <button
          type="button"
          className="btn-ghost border border-negative/40 text-negative shrink-0 inline-flex items-center gap-2"
          disabled={clearAllCompanies.isPending}
          onClick={handleClearAllCompanies}
        >
          {clearAllCompanies.isPending ? (
            <Loader2 size={16} className="animate-spin" />
          ) : (
            <Trash2 size={16} />
          )}
          Clear all company data
        </button>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Upload form */}
        <section className="lg:col-span-1 card p-5 space-y-4">
          <div>
            <h2 className="text-sm font-semibold">New document</h2>
            <p className="text-[11px] text-ink-soft mt-0.5">
              Companies, events, signals, cards all created automatically.
            </p>
          </div>

          <div className="space-y-3">
            <Field label="Company">
              <div className="flex gap-2 mb-2">
                <button
                  type="button"
                  className={clsx(
                    "flex-1 rounded-lg border px-2 py-1.5 text-xs",
                    companyMode === "existing"
                      ? "border-line bg-surface text-ink"
                      : "border-transparent text-ink-soft",
                  )}
                  onClick={() => setCompanyMode("existing")}
                >
                  Existing
                </button>
                <button
                  type="button"
                  className={clsx(
                    "flex-1 rounded-lg border px-2 py-1.5 text-xs",
                    companyMode === "new"
                      ? "border-line bg-surface text-ink"
                      : "border-transparent text-ink-soft",
                  )}
                  onClick={() => setCompanyMode("new")}
                >
                  New company
                </button>
              </div>
              {companyMode === "existing" ? (
                <select
                  className="input w-full"
                  value={companyId}
                  onChange={(e) =>
                    setCompanyId(e.target.value ? Number(e.target.value) : "")
                  }
                >
                  <option value="">Select a company…</option>
                  {companies?.map((c) => (
                    <option key={c.company_id} value={c.company_id}>
                      {c.short_name || c.company_name}
                      {c.nse_symbol ? ` (${c.nse_symbol})` : ""}
                    </option>
                  ))}
                </select>
              ) : (
                <div className="space-y-2 rounded-xl border border-line/60 p-3 bg-surface/50">
                  <input
                    className="input w-full"
                    placeholder="Legal name (required)"
                    value={newName}
                    onChange={(e) => setNewName(e.target.value)}
                  />
                  <input
                    className="input w-full"
                    placeholder="Short name"
                    value={newShortName}
                    onChange={(e) => setNewShortName(e.target.value)}
                  />
                  <input
                    className="input w-full"
                    placeholder="NSE symbol (e.g. ABC)"
                    value={newSymbol}
                    onChange={(e) => setNewSymbol(e.target.value.toUpperCase())}
                  />
                  <input
                    className="input w-full"
                    placeholder="Sector"
                    list="sector-suggestions"
                    value={newSector}
                    onChange={(e) => setNewSector(e.target.value)}
                  />
                  <datalist id="sector-suggestions">
                    {sectors?.map((s) => (
                      <option key={s.sector_id} value={s.sector_name} />
                    ))}
                  </datalist>
                  <input
                    className="input w-full"
                    placeholder="Industry (optional)"
                    value={newIndustry}
                    onChange={(e) => setNewIndustry(e.target.value)}
                  />
                  <button
                    type="button"
                    className="btn-primary w-full text-xs"
                    disabled={createCompany.isPending || !newName.trim()}
                    onClick={() => createCompany.mutate()}
                  >
                    {createCompany.isPending ? "Creating…" : "Create company"}
                  </button>
                </div>
              )}
            </Field>

            <Field label="Event type">
              <select
                className="input w-full"
                value={eventType}
                onChange={(e) => setEventType(e.target.value as EventType)}
              >
                {EVENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </Field>

            <Field label="Document type">
              <select
                className="input w-full"
                value={documentType}
                onChange={(e) => setDocumentType(e.target.value as DocumentType)}
              >
                {DOCUMENT_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ))}
              </select>
            </Field>

            <div className="grid grid-cols-2 gap-3">
              <Field label="Period" required>
                <input
                  className="input w-full"
                  value={periodLabel}
                  onChange={(e) => setPeriodLabel(e.target.value)}
                  placeholder="Q4 FY2025-26"
                  required
                />
                <p className="text-[11px] text-ink-soft mt-1">
                  Format: Q1–Q4 plus FY (e.g. Q4 FY25-26). Used as the document title; links
                  metrics and signals to that quarter.
                </p>
              </Field>
              <Field label="Event date (optional)">
                <input
                  type="date"
                  className="input w-full"
                  value={eventDate}
                  onChange={(e) => setEventDate(e.target.value)}
                />
                <p className="text-[11px] text-ink-soft mt-1">
                  Filing or result date. Overrides period label when set.
                </p>
              </Field>
            </div>

            <Field label="File or URL">
              <input
                ref={fileInput}
                type="file"
                accept=".pdf,.txt,.md,application/pdf,text/plain,text/markdown"
                className="input w-full file:mr-3 file:rounded-md file:border-0 file:bg-surface-2 file:px-3 file:py-1.5 file:text-xs file:text-ink"
                onChange={(e) => {
                  const picked = e.target.files?.[0] ?? null;
                  setFile(picked);
                  if (picked) setDocumentUrl("");
                }}
              />
              {file && (
                <div className="text-[11px] text-ink-soft mt-1">
                  {file.name} · {(file.size / 1024).toFixed(1)} KB
                </div>
              )}
              <p className="text-[11px] text-ink-soft mt-2 mb-1">Or paste a direct PDF / text URL</p>
              <input
                type="url"
                className="input w-full"
                placeholder="https://example.com/filing.pdf"
                value={documentUrl}
                onChange={(e) => {
                  setDocumentUrl(e.target.value);
                  if (e.target.value.trim()) {
                    setFile(null);
                    if (fileInput.current) fileInput.current.value = "";
                  }
                }}
              />
            </Field>

            {selectedCompany && (
              <div className="text-[11px] text-ink-soft">
                Target: <span className="text-ink">{selectedCompany.company_name}</span>
                {selectedCompany.sector_name && ` · ${selectedCompany.sector_name}`}
              </div>
            )}

            <button
              type="button"
              className="btn-primary w-full"
              disabled={
                upload.isPending ||
                !hasSource ||
                !companyId ||
                !periodLabel.trim() ||
                companyMode === "new"
              }
              onClick={() => upload.mutate()}
            >
              {upload.isPending ? (
                <>
                  <Loader2 size={14} className="animate-spin" /> Uploading…
                </>
              ) : (
                <>
                  <Upload size={14} /> Queue pipeline
                </>
              )}
            </button>

            {errorMessage && (
              <div className="rounded-lg bg-negative-bg/40 border border-negative/40 px-3 py-2 text-xs text-negative flex items-start gap-2">
                <AlertCircle size={14} className="mt-0.5 shrink-0" />
                <span>{errorMessage}</span>
              </div>
            )}
            {lastResponse && (
              <div className="rounded-lg bg-positive-bg/40 border border-positive/40 px-3 py-2 text-xs text-positive flex items-start gap-2">
                <CheckCircle2 size={14} className="mt-0.5 shrink-0" />
                <div>
                  Queued. Job #{lastResponse.job_id} created — worker will pick it up in a few
                  seconds.
                </div>
              </div>
            )}
          </div>
        </section>

        {/* Jobs queue */}
        <section className="lg:col-span-2 card p-5 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-sm font-semibold">Recent jobs</h2>
              <p className="text-[11px] text-ink-soft mt-0.5">
                Auto-refreshes every 4 s. Failed jobs show in Review Queue.
              </p>
            </div>
            <button
              type="button"
              className="btn-ghost text-xs"
              onClick={() => qc.invalidateQueries({ queryKey: ["extraction-jobs"] })}
            >
              <RefreshCcw size={13} />
              Refresh
            </button>
          </div>

          {jobsLoading ? (
            <PageLoader />
          ) : !jobs || jobs.length === 0 ? (
            <div className="text-sm text-ink-mute text-center py-10">
              No jobs yet. Upload a document to kick off the pipeline.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-[11px] uppercase tracking-wider text-ink-soft border-b border-line/60">
                  <tr>
                    <th className="px-3 py-2 text-left">Job</th>
                    <th className="px-3 py-2 text-left">Document</th>
                    <th className="px-3 py-2 text-left">Status</th>
                    <th className="px-3 py-2 text-left">Model</th>
                    <th className="px-3 py-2 text-right">Confidence</th>
                    <th className="px-3 py-2 text-right">Signals</th>
                    <th className="px-3 py-2 text-right">Cards</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.map((j) => {
                    const signals = jobSignalsCount(j);
                    const pipelineDone =
                      j.status === "COMPLETED" || j.status === "NEEDS_REVIEW";
                    const noSignalsFired = pipelineDone && signals === 0;

                    return (
                      <tr key={j.job_id} className="border-b border-line/30">
                        <td className="px-3 py-2 num text-ink-soft">#{j.job_id}</td>
                        <td className="px-3 py-2">
                          <div className="text-ink truncate max-w-[16rem]">{j.document_title}</div>
                          <div className="text-[11px] text-ink-soft">
                            {j.company_name}
                            {j.company_symbol ? ` · ${j.company_symbol}` : ""}
                          </div>
                        </td>
                        <td className="px-3 py-2">
                          <JobStatusChip status={j.status} />
                          {noSignalsFired && (
                            <div className="text-[11px] text-mixed mt-1">No signals fired</div>
                          )}
                          {j.error_message && (
                            <div className="text-[11px] text-negative mt-1 max-w-[16rem] truncate">
                              {j.error_message}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2 text-ink-soft text-xs">{j.model_name ?? "—"}</td>
                        <td className="px-3 py-2 text-right num">
                          {j.extraction_confidence != null
                            ? `${j.extraction_confidence.toFixed(0)}%`
                            : "—"}
                        </td>
                        <td className="px-3 py-2 text-right num">
                          {signals != null ? signals : "—"}
                        </td>
                        <td className="px-3 py-2 text-right num">{j.cards_generated ?? 0}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

function Field({
  label,
  children,
  required,
}: {
  label: string;
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label className="block">
      <div className="text-[11px] uppercase tracking-wider text-ink-soft mb-1">
        {label}
        {required && <span className="text-negative ml-0.5">*</span>}
      </div>
      {children}
    </label>
  );
}

function JobStatusChip({ status }: { status: ExtractionStatus }) {
  const cfg: Record<ExtractionStatus, { label: string; tone: string; icon: LucideIcon }> = {
    PENDING: { label: "Pending", tone: "chip-neutral", icon: Clock },
    PROCESSING: { label: "Processing", tone: "chip-low", icon: Loader2 },
    COMPLETED: { label: "Completed", tone: "chip-positive", icon: CheckCircle2 },
    FAILED: { label: "Failed", tone: "chip-negative", icon: AlertCircle },
    NEEDS_REVIEW: { label: "Needs review", tone: "chip-mixed", icon: FileText },
  };
  const c = cfg[status];
  const Icon = c.icon;
  return (
    <span className={clsx(c.tone, "text-[11px]")}>
      <Icon size={11} className={status === "PROCESSING" ? "animate-spin" : ""} />
      {c.label}
    </span>
  );
}
