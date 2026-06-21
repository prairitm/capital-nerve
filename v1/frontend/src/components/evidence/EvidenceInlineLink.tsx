import type { EvidenceItem } from "@/api/types";
import { SourceDocumentLink } from "@/components/common/SourceDocumentLink";

function normalizeEvidenceKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]+/g, "");
}

function expandMatchKeys(keys: string[]): string[] {
  const expanded = new Set(keys);
  for (const k of keys) {
    if (k === "pbt" || k.endsWith("topbt") || k.includes("profitbeforetax")) {
      expanded.add("pbt");
      expanded.add("profitbeforetax");
    }
    if (k.includes("otherincome") && k.includes("pbt")) {
      expanded.add("otherincometopbt");
    }
  }
  return [...expanded];
}

/** Match evidence rows whose label/value overlaps any of the given metric keys or names. */
export function evidenceMatchingLabel(
  evidence: EvidenceItem[],
  ...labels: (string | null | undefined)[]
): EvidenceItem[] {
  const keys = expandMatchKeys(
    labels
      .filter((l): l is string => Boolean(l?.trim()))
      .map((l) => normalizeEvidenceKey(l)),
  );
  if (keys.length === 0) return [];

  return evidence.filter((e) => {
    if (e.document_id == null) return false;
    const labelKey = normalizeEvidenceKey(e.evidence_label ?? "");
    const valueKey = normalizeEvidenceKey(e.evidence_value ?? "");
    return keys.some(
      (k) =>
        (labelKey && (labelKey.includes(k) || k.includes(labelKey))) ||
        (valueKey && (valueKey.includes(k) || k.includes(valueKey))),
    );
  });
}

function inlineLinkLabel(e: EvidenceItem): string {
  if (e.page_number != null) return `p.${e.page_number}`;
  return "source";
}

/** Compact document link(s) for inline placement beside a metric or value. */
export function EvidenceInlineLinks({ items }: { items: EvidenceItem[] }) {
  const linked = items.filter((e) => e.document_id != null);
  if (linked.length === 0) return null;

  return (
    <span className="inline-flex flex-wrap items-center gap-x-1 gap-y-0.5 ml-1 align-middle">
      {linked.map((e, i) => (
        <span key={e.card_evidence_id} className="inline-flex items-center">
          {i > 0 && <span className="text-ink-soft/80 text-[10px]">·</span>}
          <SourceDocumentLink
            documentId={e.document_id!}
            page={e.page_number}
            label={inlineLinkLabel(e)}
            className="text-[11px] font-normal"
          />
        </span>
      ))}
    </span>
  );
}
