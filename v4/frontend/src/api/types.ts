// Native types for the v4 frontend. These map 1:1 to the 7-step SQLite schema
// and the v4 backend serializers — no v1 intelligence-object shapes.

export type SignalDirection = "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type UserRole = "MEMBER" | "ADMIN";

export interface User {
  id: string;
  email: string;
  full_name: string | null;
  role: UserRole;
  is_active: boolean;
  must_change_password: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface TemporaryCredentialResponse {
  user: User;
  temporary_password: string;
}

export type ReviewQueueStatus = "open" | "approved" | "rejected";

export interface FactReviewCandidate {
  observation_id: string;
  document_id: string | null;
  fact_code: string;
  value: number | null;
  value_text: string | null;
  unit: string | null;
  period: string | null;
  period_type: string | null;
  basis: string | null;
  source_page: number | null;
  source_text: string | null;
  extraction_method: string | null;
  confidence: number | null;
}

export interface FactReviewDecision {
  resolved_fact_id: string;
  decision: "approved" | "rejected";
  selected_observation_id: string | null;
  reviewer_note: string | null;
  reviewed_by: string;
  reviewed_at: string;
  updated_at: string;
  application_status: "pending" | "applied" | "failed" | "not_applicable";
  applied_at: string | null;
  applied_by: string | null;
  application_error: string | null;
  recompute_status: "pending" | "succeeded" | "failed" | "not_applicable";
  recomputed_at: string | null;
  recompute_error: string | null;
  reviewer_email: string | null;
  reviewer_name: string | null;
}

export interface FactReviewItem {
  resolved_fact_id: string;
  company_id: string;
  company_name: string | null;
  company_symbol: string | null;
  event_id: string;
  event_date: string | null;
  event_title: string | null;
  fact_code: string;
  fact_name: string | null;
  resolved_value: number | null;
  resolved_value_text: string | null;
  unit: string | null;
  basis: string | null;
  period: string | null;
  period_type: string | null;
  confidence: number | null;
  selected_observation_id: string | null;
  document_id: string | null;
  document_title: string | null;
  source_page: number | null;
  source_text: string | null;
  queue_status: ReviewQueueStatus;
  decision: FactReviewDecision | null;
  candidates: FactReviewCandidate[];
}

export interface FactReviewResponse {
  items: FactReviewItem[];
  count: number;
}

export interface FactReviewSummary {
  open: number;
  approved: number;
  rejected: number;
  total: number;
}

export interface Profile {
  full_name: string | null;
  login_email: string;
  notification_email: string;
  email_enabled: boolean;
  email_verified: boolean;
  verification_required: boolean;
  financial_results_enabled: boolean;
  investor_presentations_enabled: boolean;
  earnings_calls_enabled: boolean;
}

export interface Company {
  id: string;
  name: string | null;
  ticker: string | null;
  exchange: string | null;
  sector: string | null;
  industry: string | null;
  isin: string | null;
}

export interface CompanyListItem extends Company {
  latest_event_date: string | null;
  latest_period_label: string | null;
  signal_count: number;
  highest_severity: SeverityLevel | null;
  watchlist_status: boolean;
}

export interface NseCompanySearchResult {
  symbol: string;
  name: string;
  company_name: string;
  series: string | null;
  listing_date: string | null;
  isin: string | null;
  company_id: string | null;
  coverage_status: "available" | "covered" | "watched";
}

export interface CompanyEvent {
  id: string;
  company_id: string | null;
  event_type: string;
  event_type_raw: string | null;
  event_date: string | null;
  fiscal_year: number | null;
  fiscal_quarter: number | null;
  period_label: string | null;
  title: string | null;
  source_url: string | null;
  document_id: string | null;
  status: string | null;
}

export interface ExtractedValue {
  value_code: string;
  value_name: string;
  statement: string | null;
  category: string | null;
  group: string | null;
  value_numeric: number | null;
  value_text: string | null;
  unit: string | null;
  period_type: string | null;
  period_start: string | null;
  period_end: string | null;
  basis: string | null;
  scope?: string | null;
  scope_level?: string | null;
  scope_name?: string | null;
  segment?: string | null;
  geography?: string | null;
  product?: string | null;
  channel?: string | null;
  project?: string | null;
  customer_type?: string | null;
  metric_context?: string | null;
  fact_type?: string | null;
  value_lower?: number | null;
  value_upper?: number | null;
  sentiment?: "positive" | "neutral" | "mixed" | "negative" | string | null;
  is_explicit_guidance?: boolean | number | null;
  resolution_status?: string | null;
  resolved_fact_id?: string | null;
  source_text: string | null;
  source_page: number | null;
  confidence: number | null;
  document_id?: string | null;
  observation_id?: string | null;
}

export interface SignalInputFact extends ExtractedValue {
  fact_key: string;
  scope: string;
  document_id: string | null;
}

export interface MetricValue {
  metric_code: string;
  metric_name: string;
  metric_value: number | null;
  unit: string | null;
  category: string | null;
  period_start: string | null;
  period_end: string | null;
  calculation_data: Record<string, unknown>;
}

export interface SignalEvidence {
  metric_ids?: string[];
  fact_ids?: string[];
  metric_keys?: string[];
  trigger_values?: Record<string, number>;
  rule_text?: string | null;
  category?: string | null;
}

export interface Signal {
  id: string;
  company_id: string | null;
  event_id: string | null;
  signal_type: string;
  signal_name: string;
  title: string | null;
  description: string | null;
  direction: SignalDirection | null;
  severity: SeverityLevel | null;
  category: string | null;
  confidence: number | null;
  evidence: SignalEvidence;
  detected_at: string | null;
  company: Company | null;
  event?: CompanyEvent | null;
}

export interface SnapshotRow {
  code: string;
  metric: string;
  current_value: number | null;
  previous_value: number | null;
  yoy_change_pct: number | null;
  unit: string | null;
}

export interface FactPeriod {
  period_end: string;
  period_label: string | null;
  scope: string;
  facts_count: number;
  is_current_event_period: boolean;
}

export interface DocumentInfo {
  id: string;
  company_id: string | null;
  source_url: string | null;
  title: string | null;
  document_kind: string | null;
  file_size: number | null;
  status: string | null;
  error_message: string | null;
  ingested_at: string | null;
}

export interface CompanyHub {
  company: Company;
  watchlist_status: boolean;
  latest_event_id: string | null;
  latest_period_label: string | null;
  latest_period_events: CompanyEvent[];
  financial_snapshot: SnapshotRow[];
  latest_metrics: MetricValue[];
  signals: Signal[];
  timeline: CompanyEvent[];
  documents: DocumentInfo[];
}

export interface EventDetail {
  event: CompanyEvent;
  company: Company | null;
  intelligence_status: {
    state: "processing" | "ready";
    pending_facts: number;
    verified_facts: number;
  };
  facts: ExtractedValue[];
  fact_periods: FactPeriod[];
  selected_fact_period_end: string | null;
  metrics: MetricValue[];
  signals: Signal[];
  financial_snapshot: SnapshotRow[];
  related_events: CompanyEvent[];
  document_sections?: QuarterDocumentSection[];
  quarter_display?: QuarterDisplayConfig | null;
  event_summary: EventSummary | null;
}

export interface EventSummary {
  event_id: string;
  document_id: string;
  model: string;
  headline: string;
  summary: string;
  key_points: string[];
  investor_takeaway: string;
  generated_at: string;
  cached: boolean;
}

export interface DisplayFactGroup {
  key: string;
  label: string;
  description?: string | null;
  max_items: number;
  fact_codes: string[];
}

export interface DocumentDisplayConfig {
  question?: string | null;
  max_headlines?: number;
  max_signals?: number;
  headline_facts?: string[];
  headline_metrics?: string[];
  metric_priority?: string[];
  signal_priority?: string[];
  signal_groups?: Record<string, string>;
  fact_groups?: DisplayFactGroup[];
}

export interface QuarterDisplayConfig {
  title?: string | null;
  max_items?: number;
  source_order?: string[];
}

export interface QuarterDocumentSection {
  key: string;
  document_type: string;
  label: string;
  event: CompanyEvent | null;
  document: DocumentInfo | null;
  facts: ExtractedValue[];
  fact_periods: FactPeriod[];
  selected_fact_period_end: string | null;
  metrics: MetricValue[];
  signals: Signal[];
  display?: DocumentDisplayConfig | null;
  presentation_summary?: PresentationSummary | null;
  counts: {
    facts: number;
    metrics: number;
    signals: number;
  };
}

export interface PresentationSegment {
  name: string;
  slug: string | null;
  aliases: string | null;
  slides: string | null;
  confidence: number | null;
}

export interface PresentationSummary {
  segments: PresentationSegment[];
  scope_counts: Record<string, number>;
  fact_type_counts: Record<string, number>;
  guidance_count: number;
  average_confidence: number | null;
}

export interface SignalDetail extends Signal {
  rule: Record<string, unknown> | null;
  rule_text: string | null;
  trigger_values: Record<string, number>;
  metric_keys: string[];
  referenced_metrics: MetricValue[];
  input_facts: SignalInputFact[];
  event: CompanyEvent | null;
}

export interface TrendSeries {
  metric_code: string;
  metric_name: string;
  unit: string | null;
  points: { period_end: string | null; value: number | null }[];
}

export interface FeedSummary {
  processed_filings: number;
  total_signals: number;
  total: number;
  positive: number;
  negative: number;
  mixed: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
}

export interface FeedItem {
  company: Company;
  event: CompanyEvent;
  document: DocumentInfo | null;
  signals: Signal[];
  detail_path: string | null;
}

export interface DocumentDetail {
  document: DocumentInfo;
  company: Company | null;
  event: CompanyEvent | null;
  counts: {
    extracted_values: number;
    metric_values: number;
    signals: number;
  };
  filing_summary: {
    available_fact_count: number;
    highlights: ExtractedValue[];
  } | null;
}

export interface SourceLocateResult {
  page: number | null;
  reference_text: string | null;
  bbox: number[] | null;
}

export interface WatchlistResponse {
  companies: CompanyListItem[];
  count: number;
}

export interface WatchlistMutationResponse {
  watchlist_status: boolean;
  added?: boolean;
  removed?: boolean;
  company?: Company;
}
