export type SignalDirection = "POSITIVE" | "NEGATIVE" | "MIXED" | "NEUTRAL";
export type SeverityLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
export type ConfidenceLevel = "HIGH" | "MEDIUM" | "LOW" | "NEEDS_REVIEW";
export type EventType =
  | "QUARTERLY_RESULT"
  | "CONCALL_TRANSCRIPT"
  | "INVESTOR_PRESENTATION"
  | "PRESS_RELEASE"
  | "EXCHANGE_FILING"
  | "SHAREHOLDING_PATTERN"
  | "ANNUAL_REPORT"
  | "CREDIT_RATING";
export type DocumentType =
  | "FINANCIAL_RESULT"
  | "CONCALL_TRANSCRIPT"
  | "INVESTOR_PRESENTATION"
  | "PRESS_RELEASE"
  | "EXCHANGE_FILING"
  | "ANNUAL_REPORT"
  | "CREDIT_RATING_REPORT";

export interface UserPayload {
  user_id: number;
  email: string | null;
  full_name: string | null;
  user_type: "RETAIL" | "ANALYST" | "INSTITUTION" | "ADMIN";
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
  user_id: number;
  email: string;
  user_type: UserPayload["user_type"];
  full_name: string | null;
}

export interface CompanyBrief {
  company_id: number;
  company_name: string;
  short_name: string | null;
  nse_symbol: string | null;
  bse_code: string | null;
  sector_name: string | null;
  industry: string | null;
  market_cap_cr: number | null;
  last_price: number | null;
}

export interface PeriodBrief {
  period_id: number;
  display_label: string;
  fy_label: string;
  quarter: number | null;
  period_end_date: string;
}

export interface CardMetric {
  name: string;
  value: string | number;
  unit?: string | null;
}

export interface CardBrief {
  card_id: number;
  signal_id: number | null;
  card_type: string;
  headline: string;
  one_line_summary: string;
  signal_direction: SignalDirection | null;
  severity: SeverityLevel | null;
  confidence_score: number | null;
  confidence_level: ConfidenceLevel | null;
  card_priority: number;
  company: CompanyBrief;
  period: PeriodBrief | null;
  event_id: number | null;
  event_type: EventType | null;
  event_title: string | null;
  event_date: string | null;
  metrics_json: CardMetric[];
  watch_next: string | null;
  source_label: string | null;
  document_id: number | null;
  created_at: string;
}

export interface EvidenceItem {
  card_evidence_id: number;
  document_id: number | null;
  evidence_type: string;
  evidence_label: string | null;
  evidence_value: string | null;
  source_text: string | null;
  page_number: number | null;
  calculation_text: string | null;
  confidence_score: number | null;
}

export interface CardMetricComparison {
  metric_code: string;
  metric_name: string;
  current_value: number | null;
  previous_value: number | null;
  change_percent: number | null;
  change_bps: number | null;
  unit: string;
  comparison_type: string | null;
}

export interface ConcernHeatmapRow {
  topic: string;
  count: number;
  percent: number;
}

export interface CardDetail extends CardBrief {
  detailed_explanation: string | null;
  investor_question: string | null;
  action_label: string | null;
  calculations_json: Record<string, unknown>;
  evidence: EvidenceItem[];
  event_summary: string | null;
  event_main_issue: string | null;
  metric_comparisons: CardMetricComparison[];
  trend_sparklines: FinancialTrend[];
  concern_heatmap: ConcernHeatmapRow[];
}

export interface FeedSummary {
  results_processed: number;
  positive_signals: number;
  negative_signals: number;
  margin_warnings: number;
  red_flags: number;
  guidance_updates: number;
  verdicts: number;
  growth: number;
  margins: number;
  risks: number;
}

export interface CompanyBadge {
  label: string;
  value: string;
  tone: "positive" | "negative" | "mixed" | "neutral";
}

export interface TimelineEvent {
  event_id: number;
  event_type: EventType;
  event_title: string;
  event_date: string;
  overall_signal: SignalDirection | null;
  overall_severity: SeverityLevel | null;
  summary_text: string | null;
  period?: PeriodBrief | null;
}

export interface FinancialSnapshotRow {
  metric: string;
  code: string;
  current_value: number | null;
  previous_value: number | null;
  yoy_change_pct: number | null;
  unit: string;
}

export interface FinancialTrendPoint {
  period_label: string;
  period_end_date: string;
  value: number | null;
}

export interface FinancialTrend {
  metric_code: string;
  metric_name: string;
  unit: string;
  points: FinancialTrendPoint[];
}

export interface DocumentBrief {
  document_id: number;
  document_type: DocumentType;
  document_title: string;
  document_date: string | null;
  extraction_confidence: number | null;
  values_extracted: number | null;
  cards_generated: number | null;
}

export interface CompanyDetail {
  company: CompanyBrief;
  watchlist_status: boolean;
  badges: CompanyBadge[];
  latest_event_id: number | null;
  latest_period: PeriodBrief | null;
  latest_summary: string | null;
  main_issue: string | null;
  watch_next: string | null;
  top_objects: IntelligenceObjectBrief[];
  financial_snapshot: FinancialSnapshotRow[];
  trends: FinancialTrend[];
  timeline: TimelineEvent[];
  documents: DocumentBrief[];
}

export interface EventIngestionStatus {
  published_card_count: number;
  unpublished_card_count: number;
  published_signal_count: number;
  unpublished_signal_count: number;
  document_count: number;
  values_extracted_total: number;
}

export interface EventDetail {
  event_id: number;
  event_type: EventType;
  event_title: string;
  event_date: string;
  source_exchange: string | null;
  consolidation: string | null;
  audit_status: string | null;
  overall_signal: SignalDirection | null;
  overall_severity: SeverityLevel | null;
  overall_confidence: number | null;
  summary_text: string | null;
  main_issue: string | null;
  watch_next: string | null;
  company: CompanyBrief | null;
  period: PeriodBrief | null;
  cards: CardBrief[];
  signals: SignalBriefV1[];
  financial_snapshot: FinancialSnapshotRow[];
  related_events: TimelineEvent[];
  ingestion_status: EventIngestionStatus;
  documents: DocumentBrief[];
  concern_heatmap: { topic: string; count: number; percent: number }[];
  concall_facts: {
    fact_type: string;
    topic: string | null;
    extracted_claim: string;
    direction: SignalDirection | null;
    severity: SeverityLevel | null;
    target_period: string | null;
    document_id: number | null;
    document_title: string | null;
    page_number: number | null;
  }[];
}

export interface SignalRow {
  signal_id: number;
  signal_code: string;
  signal_name: string;
  signal_category: string;
  direction: SignalDirection;
  severity: SeverityLevel;
  confidence_score: number | null;
  signal_score?: number | null;
  headline: string | null;
  explanation: string | null;
  metric_refs: unknown[];
  evidence_refs?: unknown[];
  company: CompanyBrief;
  period: PeriodBrief | null;
  event_id: number | null;
  document_id?: number | null;
  created_at?: string | null;
}

export interface SignalEventBrief {
  event_id: number;
  event_type: EventType;
  event_title: string;
  event_date: string;
  summary_text: string | null;
  main_issue: string | null;
  watch_next: string | null;
  overall_signal: SignalDirection | null;
  overall_severity: SeverityLevel | null;
  overall_confidence: number | null;
}

export interface SignalPrimaryMetric {
  metric_code: string;
  metric_name: string;
  value: number | null;
  unit: string;
}

export interface SignalRuleLeaf {
  metric_code: string;
  metric_name: string;
  current_value: number | null;
  unit: string;
  operator: string | null;
  threshold: number | null;
  passed: boolean | null;
  rule_text: string | null;
}

export interface SignalDetail extends SignalRow {
  description: string | null;
  rule_text: string | null;
  rule_json: Record<string, unknown>;
  rule_summary: string | null;
  rule_metric_codes: string[];
  rule_leaves: SignalRuleLeaf[];
  primary_metric: SignalPrimaryMetric | null;
  signal_score: number | null;
  evidence_refs: unknown[];
  document_id: number | null;
  created_at: string | null;
  event: SignalEventBrief | null;
  document: DocumentBrief | null;
  metric_comparisons: CardMetricComparison[];
  trend_sparklines: FinancialTrend[];
  related_cards: CardBrief[];
  related_signals: Pick<
    SignalRow,
    "signal_id" | "signal_code" | "signal_name" | "signal_category" | "direction" | "severity" | "headline" | "confidence_score" | "signal_score"
  >[];
  evidence: EvidenceItem[];
  trigger_metric: CardMetricComparison | null;
}

export interface WatchlistResponse {
  watchlist_id: number;
  name: string;
  summary: {
    tracked: number;
    new_events: number;
    negative_signals: number;
    positive_signals: number;
    red_flags: number;
  };
  companies: {
    company: CompanyBrief;
    latest_signal: SignalDirection | null;
    latest_card_type: string | null;
    latest_card_headline: string | null;
    watch_next: string | null;
    severity: SeverityLevel | null;
  }[];
}

export interface WatchItem {
  watch_item_id: number;
  company_id: number;
  company_name: string;
  company_symbol: string | null;
  card_id: number | null;
  metric_def_id: number | null;
  title: string;
  description: string | null;
  current_value: number | null;
  target_value: number | null;
  condition_operator: string | null;
  condition_json: Record<string, unknown>;
  is_active: boolean;
  created_at: string;
}

export interface AlertItem {
  alert_id: number;
  alert_title: string;
  alert_message: string;
  severity: SeverityLevel | null;
  is_read: boolean;
  created_at: string;
  company_name: string | null;
  company_symbol: string | null;
  event_id: number | null;
  card_id: number | null;
}

export interface SearchResult {
  companies: CompanyBrief[];
  events: {
    event_id: number;
    event_type: EventType;
    event_title: string;
    event_date: string;
    company_name: string;
    company_symbol: string | null;
  }[];
  cards: {
    card_id: number;
    card_type: string;
    headline: string;
    one_line_summary: string;
    signal_direction: SignalDirection | null;
    severity: SeverityLevel | null;
    company_name: string;
    company_symbol: string | null;
  }[];
  document_hits: DocumentSearchHit[];
}

export interface DocumentSearchHit {
  document_id: number;
  page_number: number;
  snippet: string;
  document_type: DocumentType;
  document_title: string;
  company_id: number;
  company_name: string;
  company_symbol: string | null;
  rank: number;
}

export interface AskRequest {
  q: string;
  company_id?: number | null;
  event_id?: number | null;
}

export interface AskCitation {
  page_id: number;
  document_id: number;
  page_number: number;
  quote: string;
}

export interface AskResponse {
  answer: string;
  mode: "sql" | "rag";
  citations: AskCitation[];
  retrieval_mode: "hybrid" | "fts_only" | null;
  sql: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}

export interface DataAskRequest {
  q: string;
}

export interface DataAskResponse {
  answer: string;
  sql: string;
  columns: string[];
  rows: Record<string, unknown>[];
  row_count: number;
}

export interface DocumentDetail {
  document_id: number;
  document_type: DocumentType;
  document_title: string;
  has_source_file: boolean;
  source_content_type: string | null;
  document_date: string | null;
  extraction_confidence: number | null;
  extraction_status: string;
  values_extracted: number | null;
  cards_generated: number | null;
  page_count: number | null;
  company: { company_id: number; company_name: string; symbol: string | null } | null;
  pages: { page_id: number; page_number: number; page_markdown: string | null; page_text: string | null }[];
  cards: {
    card_id: number;
    card_type: string;
    headline: string;
    one_line_summary: string;
    signal_direction: SignalDirection | null;
    severity: SeverityLevel | null;
  }[];
  evidence: {
    card_evidence_id: number;
    card_id: number;
    evidence_type?: string | null;
    evidence_label: string | null;
    evidence_value: string | null;
    source_text: string | null;
    page_number: number | null;
    calculation_text: string | null;
    confidence_score: number | null;
  }[];
}

export interface SignalSkip {
  signal_code: string;
  signal_name: string;
  reason: string;
  detail: string;
}

export interface SignalFired {
  signal_code: string;
  signal_name: string;
  headline: string;
}

export interface SignalDiagnostics {
  fired_count: number;
  rules_total: number;
  rules_evaluable: number;
  rules_non_evaluable: number;
  blockers: string[];
  fired: SignalFired[];
  not_fired: SignalSkip[];
}

export interface ReviewItem {
  review_id: number;
  review_type: string;
  priority: SeverityLevel;
  status: string;
  issue_description: string | null;
  created_at: string;
  resolved_at: string | null;
  company_id: number | null;
  company_name: string | null;
  company_symbol: string | null;
  document_id: number | null;
  document_title: string | null;
  document_type: DocumentType | null;
  extraction_status: string | null;
  extraction_confidence: number | null;
  event_id: number | null;
  pipeline_stages: Record<string, number>;
  cards_generated: number;
  job_status: string | null;
  job_error: string | null;
  auto_publish_threshold: number;
  auto_published: boolean;
  publish_blocked_reasons: string[];
  signal_diagnostics: SignalDiagnostics | null;
}

export interface ReviewPipelineExtracted {
  extracted_value_id: number;
  label: string;
  raw_label: string;
  normalized_label: string | null;
  value: number | string | null;
  unit: string | null;
  page_number: number | null;
  confidence_score: number | null;
  statement_type: string | null;
}

export interface ReviewPipelineFact {
  fact_id: number;
  normalized_code: string;
  display_name: string;
  value: number;
  unit: string;
  period_value_type: string;
  consolidation: string;
  confidence_score: number | null;
}

export interface ReviewPipelineMetric {
  metric_id: number;
  metric_code: string;
  metric_name: string;
  metric_value: number | null;
  unit: string | null;
  comparison_type: string | null;
  change_percent: number | null;
  change_absolute: number | null;
  confidence_score: number | null;
}

export interface ReviewPipelineSignal {
  signal_id: number;
  signal_code: string;
  signal_name: string;
  signal_direction: SignalDirection;
  severity: SeverityLevel;
  headline: string | null;
  is_published: boolean;
  confidence_score: number | null;
}

export interface ReviewPipelineCard {
  card_id: number;
  card_type: string;
  headline: string;
  one_line_summary: string;
  signal_direction: SignalDirection | null;
  severity: SeverityLevel | null;
  is_published: boolean;
  card_priority: number;
}

export interface ReviewPipelineJob {
  job_id: number;
  status: string;
  model_name: string | null;
  started_at: string | null;
  completed_at: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  error_message: string | null;
  stages: Record<string, number>;
  auto_published: boolean;
  auto_publish_threshold: number;
}

export interface ReviewPipelineDetail {
  review_id: number;
  document_id: number | null;
  event_id: number | null;
  period: PeriodBrief | null;
  job: ReviewPipelineJob | null;
  extraction_confidence: number | null;
  extracted_values: ReviewPipelineExtracted[];
  facts: ReviewPipelineFact[];
  metrics: ReviewPipelineMetric[];
  signals: ReviewPipelineSignal[];
  cards: ReviewPipelineCard[];
  signal_diagnostics: SignalDiagnostics | null;
}

// ---------------------------------------------------------------------------
// v1 enterprise API
//
// Mirrors backend/app/schemas/v1/. Additive on top of the existing types —
// existing pages keep using `CardBrief` / `CardDetail`, the upgraded drawer
// and the new Intelligence Object page consume these shapes instead.
// ---------------------------------------------------------------------------

export interface EventRawFacts {
  line_item_code: string;
  line_item_name: string;
  value: number;
  unit: string;
  period_value_type: string;
  consolidation: string | null;
}

export interface EventBriefV1 {
  event_id: number;
  event_type: EventType;
  event_title: string;
  event_date: string;
  company?: CompanyBrief | null;
  period?: PeriodBrief | null;
  source_exchange: string | null;
  consolidation: string | null;
  overall_signal: SignalDirection | null;
  overall_severity: SeverityLevel | null;
  overall_confidence: number | null;
  summary_text: string | null;
  document_id: number | null;
}

export interface EventIngestionStatusV1 {
  published_card_count: number;
  unpublished_card_count: number;
  published_signal_count: number;
  unpublished_signal_count: number;
  document_count: number;
  values_extracted_total: number;
}

export interface EventConcallFactV1 {
  fact_type: string;
  topic: string | null;
  extracted_claim: string;
  direction: SignalDirection | null;
  severity: SeverityLevel | null;
  target_period: string | null;
  document_id: number | null;
  document_title: string | null;
  page_number: number | null;
}

export type AnalystSummaryTone = "positive" | "negative" | "mixed" | "neutral";

export interface AnalystSummaryTheme {
  label: string;
  tone: AnalystSummaryTone;
  sentence: string;
  evidence_ids: number[];
}

export interface AnalystSummary {
  verdict: AnalystSummaryTone;
  themes: AnalystSummaryTheme[];
}

export interface EventDetailV1 extends EventBriefV1 {
  main_issue: string | null;
  watch_next: string | null;
  audit_status: string | null;
  raw_facts: EventRawFacts[];
  documents: DocumentBrief[];
  metric_snapshot: Record<string, unknown>;
  cards: CardBrief[];
  signals: SignalBriefV1[];
  financial_snapshot: FinancialSnapshotRow[];
  related_events: TimelineEvent[];
  concern_heatmap: ConcernHeatmapRow[];
  concall_facts: EventConcallFactV1[];
  ingestion_status: EventIngestionStatusV1;
  analyst_summary: AnalystSummary | null;
}

export interface SignalCalculation {
  metric_code: string | null;
  operator: string | null;
  threshold: number | null;
  current_value: number | null;
  previous_value: number | null;
  change_percent: number | null;
  change_bps: number | null;
  unit: string | null;
  rule_text: string | null;
}

export interface SignalBriefV1 {
  signal_id: number;
  signal_code: string;
  signal_name: string;
  signal_category: string;
  direction: SignalDirection;
  severity: SeverityLevel;
  confidence_score: number | null;
  signal_score: number | null;
  headline: string | null;
  explanation: string | null;
  company?: CompanyBrief | null;
  period?: PeriodBrief | null;
  event_id: number | null;
  document_id: number | null;
  created_at: string | null;
}

export interface SignalRuleLeafV1 {
  metric_code: string;
  metric_name: string;
  current_value: number | null;
  unit: string;
  operator: string | null;
  threshold: number | null;
  passed: boolean | null;
  rule_text: string | null;
}

export interface SignalPrimaryMetricV1 {
  metric_code: string;
  metric_name: string;
  value: number | null;
  unit: string;
}

export interface SignalEventBriefV1 {
  event_id: number;
  event_type: string;
  event_title: string;
  event_date: string;
  summary_text: string | null;
  main_issue: string | null;
  watch_next: string | null;
  overall_signal: SignalDirection | null;
  overall_severity: SeverityLevel | null;
  overall_confidence: number | null;
}

export interface SignalRelatedBriefV1 {
  signal_id: number;
  signal_code: string;
  signal_name: string;
  signal_category: string;
  direction: SignalDirection;
  severity: SeverityLevel;
  confidence_score: number | null;
  signal_score: number | null;
  headline: string | null;
}

export interface SignalDetailV1 extends SignalBriefV1 {
  description: string | null;
  rule_text: string | null;
  rule_summary: string | null;
  rule_json: Record<string, unknown>;
  rule_metric_codes: string[];
  rule_leaves: SignalRuleLeafV1[];
  calculation: SignalCalculation | null;
  primary_metric: SignalPrimaryMetricV1 | null;
  trigger_metric: CardMetricComparison | null;
  metric_refs: unknown[];
  evidence_refs: unknown[];
  metric_comparisons: CardMetricComparison[];
  trend_sparklines: FinancialTrend[];
  related_cards: CardBrief[];
  related_signals: SignalRelatedBriefV1[];
  evidence: EvidenceItem[];
  event: SignalEventBriefV1 | null;
  document: DocumentBrief | null;
}

export interface IOMetric {
  name: string;
  value: string | number | null;
  unit: string | null;
}

export interface IODisplayConfig {
  layout: string;
  primary_metric: string | null;
  chart_type: string | null;
  cta: string | null;
  surfaces: string[];
}

export interface IntelligenceObjectBrief {
  intelligence_object_id: number;
  object_type: string;
  title: string;
  subtitle: string;
  status: SignalDirection | null;
  importance_score: number;
  severity: SeverityLevel | null;
  confidence: ConfidenceLevel | null;
  confidence_score: number | null;
  time_horizon: string;
  company: CompanyBrief;
  period: PeriodBrief | null;
  event_id: number | null;
  event_type: EventType | null;
  event_title: string | null;
  event_date: string | null;
  signal_id: number | null;
  primary_metric: string | null;
  investor_relevance: string[];
  source_label: string | null;
  document_id: number | null;
  created_at: string;
}

export interface CalculationChainInput {
  formula_name: string;
  code: string | null;
  scope: string;
  kind: "fact" | "metric";
  value: number | null;
  unit: string | null;
  document_id: number | null;
  page_number: number | null;
  source_text: string | null;
}

export interface CalculationChainMetric {
  code: string | null;
  name: string | null;
  formula_text: string | null;
  value: number | null;
  unit: string | null;
  inputs: CalculationChainInput[];
  is_quarantined: boolean;
  quarantine_reason: string | null;
}

export interface CalculationChainSignal {
  code: string | null;
  name: string | null;
  category: string | null;
  rule_text: string | null;
  direction: SignalDirection | null;
  severity: SeverityLevel | null;
  fired_value: number | null;
  fired_unit: string | null;
  threshold: number | null;
  operator: string | null;
  metric_ref: string | null;
}

export interface CalculationChain {
  signal: CalculationChainSignal | null;
  metric: CalculationChainMetric | null;
}

export interface IntelligenceObject {
  intelligence_object_id: number;
  object_type: string;
  title: string;
  subtitle: string;
  status: SignalDirection | null;
  importance_score: number;
  severity: SeverityLevel | null;
  confidence: ConfidenceLevel | null;
  confidence_score: number | null;
  time_horizon: string;
  investor_relevance: string[];
  insight: string | null;
  investor_question: string | null;
  watch_next: string | null;
  company: CompanyBrief;
  period: PeriodBrief | null;
  event: EventBriefV1 | null;
  signal: SignalBriefV1 | null;
  metrics: IOMetric[];
  metric_comparisons: CardMetricComparison[];
  trend_sparklines: FinancialTrend[];
  concern_heatmap: ConcernHeatmapRow[];
  calculation: Record<string, unknown>;
  calculation_chain: CalculationChain | null;
  evidence: EvidenceItem[];
  display: IODisplayConfig;
  suggested_actions: string[];
  source_label: string | null;
  document_id: number | null;
  event_main_issue: string | null;
  event_summary: string | null;
  created_at: string;
}

export interface PortfolioMonitorRequest {
  symbols: string[];
  min_importance?: number | null;
  severity_in?: SeverityLevel[] | null;
  direction_in?: SignalDirection[] | null;
  limit_per_company?: number;
}

export interface PortfolioAlert {
  company: CompanyBrief;
  matched: boolean;
  reason: string | null;
  top_objects: IntelligenceObjectBrief[];
  triggered_at: string | null;
}

export interface PortfolioMonitorResponse {
  requested_symbols: string[];
  resolved_companies: number;
  unresolved_symbols: string[];
  alerts: PortfolioAlert[];
}

export interface SectorSignalRow {
  signal_id: number;
  signal_code: string;
  signal_name: string;
  signal_category: string;
  direction: SignalDirection;
  severity: SeverityLevel;
  confidence_score: number | null;
  signal_score: number | null;
  headline: string | null;
  company: CompanyBrief;
  period: PeriodBrief | null;
  event_id: number | null;
}

export interface SectorSignalsResponse {
  sector_name: string;
  company_count: number;
  signal_count: number;
  signals: SectorSignalRow[];
}

export interface NarrativeTheme {
  topic: string;
  count: number;
  sample_claim: string | null;
}

export interface PeerCompanyThemes {
  company: CompanyBrief;
  themes: NarrativeTheme[];
}

export interface PeerNarrativeComparison {
  company: CompanyBrief;
  company_narrative: NarrativeTheme[];
  peer_narratives: PeerCompanyThemes[];
  positioning_gap: string | null;
  over_communicated_topics: string[];
  under_communicated_topics: string[];
}

export type CreditDimension =
  | "debt"
  | "coverage"
  | "working_capital"
  | "earnings_quality"
  | "auditor"
  | "rating"
  | "other";

export interface CreditRiskSignal {
  signal_id: number;
  signal_code: string;
  signal_name: string;
  signal_category: string;
  credit_dimension: CreditDimension;
  direction: SignalDirection;
  severity: SeverityLevel;
  confidence_score: number | null;
  signal_score: number | null;
  headline: string | null;
  explanation: string | null;
  period: PeriodBrief | null;
  event_id: number | null;
  created_at: string | null;
}

export interface CreditRiskResponse {
  company: CompanyBrief;
  overall_risk: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  rationale: string | null;
  signals: CreditRiskSignal[];
}

export interface RetailSummaryPoint {
  label: string;
  tone: "positive" | "negative" | "mixed" | "neutral";
  detail: string | null;
}

export interface RetailSummary {
  company: CompanyBrief;
  period: PeriodBrief | null;
  simple_summary: string;
  risk_level: "LOW" | "MEDIUM" | "HIGH" | "CRITICAL";
  momentum: "positive" | "negative" | "mixed" | "neutral";
  top_3_points: RetailSummaryPoint[];
  headline_metrics: { name?: string; value?: number | string | null; unit?: string }[];
}

export interface ResultBriefPoint {
  title: string;
  detail: string | null;
  metric_code: string | null;
  value: number | string | null;
  unit: string | null;
}

export interface ResultPeerComparison {
  metric_code: string;
  metric_name: string;
  company_value: number | null;
  peer_median: number | null;
  rank: number | null;
  sample_size: number;
  unit: string;
}

export interface ResultBrief {
  company: CompanyBrief;
  period: PeriodBrief | null;
  event_id: number | null;
  headline: string;
  overall_verdict: string | null;
  key_positives: ResultBriefPoint[];
  key_negatives: ResultBriefPoint[];
  model_update_fields: Record<string, number | string | null>;
  peer_comparison: ResultPeerComparison[];
  metric_comparisons: CardMetricComparison[];
  source_evidence: EvidenceItem[];
}

// ---------------------------------------------------------------------------
// Ingestion pipeline
// ---------------------------------------------------------------------------

export type ExtractionStatus =
  | "PENDING"
  | "PROCESSING"
  | "COMPLETED"
  | "FAILED"
  | "NEEDS_REVIEW";

export interface IngestUploadResponse {
  queued: boolean;
  event_id: number;
  document_id: number;
  job_id: number;
  review_id: number;
  file_hash: string;
  size_bytes: number;
}

export interface SectorBrief {
  sector_id: number;
  sector_name: string;
  industry: string | null;
}

export interface CreateCompanyResponse {
  company: CompanyBrief;
}

export interface ClearAllCompaniesResponse {
  companies_removed: number;
  symbols: string[];
}

export interface ExtractionJobBrief {
  job_id: number;
  document_id: number;
  company_id: number;
  company_name: string;
  company_symbol: string | null;
  document_title: string;
  document_type: DocumentType;
  status: ExtractionStatus;
  model_name: string | null;
  started_at: string | null;
  completed_at: string | null;
  input_tokens: number | null;
  output_tokens: number | null;
  cost_usd: number | null;
  extraction_confidence: number | null;
  values_extracted: number | null;
  cards_generated: number | null;
  error_message: string | null;
  meta: Record<string, unknown>;
  created_at: string;
}
