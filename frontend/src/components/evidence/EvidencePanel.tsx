import clsx from "clsx";
import type { EvidenceItem } from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";
import {
  confidenceTone,
  formatEvidenceValue,
  formatExtractionConfidence,
} from "@/lib/format";

interface Props {
  evidence: EvidenceItem[];
  title?: string;
  subtitle?: string;
  className?: string;
  /** Limit rows; pass `null` for "show all". Default 8. */
  limit?: number | null;
}

function evidenceTypeLabel(type: string | null | undefined): string | null {
  if (!type) return null;
  switch (type) {
    case "source_quote":
      return "Quote";
    case "extracted_value":
      return "Extracted value";
    case "calculated_metric":
      return "Calculated";
    case "narrative":
      return "Narrative";
    case "management_statement":
      return "Mgmt statement";
    default:
      return type.replace(/_/g, " ");
  }
}

function EvidenceRow({ item }: { item: EvidenceItem }) {
  const formattedValue = formatEvidenceValue(item.evidence_value);
  const typeLabel = evidenceTypeLabel(item.evidence_type);

  return (
    <li className="border-t border-line/40 first:border-t-0 py-3 first:pt-0 last:pb-0 space-y-1.5">
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          {item.evidence_label && (
            <div className="text-xs font-medium text-ink truncate">
              {item.evidence_label}
            </div>
          )}
          {typeLabel && (
            <div className="text-[11px] text-ink-soft mt-0.5 uppercase tracking-wider">
              {typeLabel}
            </div>
          )}
        </div>
        {formattedValue && (
          <div className="num text-sm font-semibold text-ink shrink-0">
            {formattedValue}
          </div>
        )}
      </div>

      {item.source_text && (
        <p className="text-xs text-ink-mute italic border-l-2 border-line pl-3 leading-relaxed">
          “{item.source_text.trim()}”
        </p>
      )}

      {item.calculation_text && (
        <p className="text-[11px] font-mono text-ink-soft bg-surface-2/60 rounded-md px-2 py-1 leading-relaxed">
          {item.calculation_text}
        </p>
      )}

      <div className="flex items-center justify-between gap-3 text-[11px] text-ink-soft">
        {item.document_id != null ? (
          <SourceDocumentLink
            documentId={item.document_id}
            page={item.page_number ?? undefined}
            label={item.page_number != null ? `Open p.${item.page_number}` : "Open source"}
            className="text-[11px] font-normal"
          />
        ) : (
          <span>No document link</span>
        )}
        {item.confidence_score != null && (
          <span
            className={clsx("num", confidenceTone(item.confidence_score))}
            title="Extraction confidence (0–100)"
          >
            {formatExtractionConfidence(item.confidence_score)} conf
          </span>
        )}
      </div>
    </li>
  );
}

/**
 * Shared evidence list used on intelligence-object, card-drawer, and event
 * surfaces. Each row links into the document viewer at the right page so the
 * analyst can verify the underlying quote in one click.
 */
export function EvidencePanel({
  evidence,
  title = "Evidence",
  subtitle,
  className,
  limit = 8,
}: Props) {
  if (!evidence || evidence.length === 0) return null;

  const rows = limit === null ? evidence : evidence.slice(0, limit);
  const hidden = limit !== null ? Math.max(0, evidence.length - rows.length) : 0;

  return (
    <section className={clsx("card p-5 md:p-6 space-y-3", className)}>
      <header>
        <div className="flex items-baseline justify-between gap-3">
          <h2 className="text-base font-semibold">{title}</h2>
          <span className="text-[11px] text-ink-soft">
            {evidence.length} {evidence.length === 1 ? "row" : "rows"}
          </span>
        </div>
        {subtitle && <p className="text-xs text-ink-soft mt-0.5">{subtitle}</p>}
      </header>
      <ul>
        {rows.map((item) => (
          <EvidenceRow key={item.card_evidence_id} item={item} />
        ))}
      </ul>
      {hidden > 0 && (
        <p className="text-[11px] text-ink-soft">
          {hidden} more {hidden === 1 ? "row" : "rows"} on the document page.
        </p>
      )}
    </section>
  );
}
