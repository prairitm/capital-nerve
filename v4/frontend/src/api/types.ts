// Native types for the v4 frontend. These map 1:1 to the 7-step SQLite schema
// and the v4 backend serializers — no v1 intelligence-object shapes.

export type SignalDirection = "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";

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
  facts: ExtractedValue[];
  fact_periods: FactPeriod[];
  selected_fact_period_end: string | null;
  metrics: MetricValue[];
  signals: Signal[];
  financial_snapshot: SnapshotRow[];
  related_events: CompanyEvent[];
  document_sections?: QuarterDocumentSection[];
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
  total: number;
  positive: number;
  negative: number;
  mixed: number;
  by_category: Record<string, number>;
  by_severity: Record<string, number>;
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
}

export interface SourceLocateResult {
  page: number | null;
  reference_text: string | null;
  bbox: number[] | null;
}
