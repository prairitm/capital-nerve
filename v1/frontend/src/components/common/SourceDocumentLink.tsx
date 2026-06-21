import type { MouseEvent } from "react";
import { Link } from "react-router-dom";
import clsx from "clsx";
import type { EvidenceItem } from "@/api/types";

export type SourceRef = {
  documentId: number;
  page?: number | null;
  label: string;
};

export function documentSourceHref(documentId: number, page?: number | null): string {
  return page != null ? `/documents/${documentId}?page=${page}` : `/documents/${documentId}`;
}

/** Dedupe document + page refs from card evidence and optional primary document. */
export function uniqueSourceRefs(
  evidence: EvidenceItem[],
  primary?: { documentId: number; label?: string | null } | null,
): SourceRef[] {
  const seen = new Set<string>();
  const out: SourceRef[] = [];

  const add = (documentId: number, page: number | null | undefined, label: string) => {
    const key = `${documentId}:${page ?? ""}`;
    if (seen.has(key)) return;
    seen.add(key);
    out.push({ documentId, page: page ?? undefined, label });
  };

  if (primary?.documentId) {
    add(primary.documentId, null, primary.label?.trim() || "Source document");
  }

  for (const e of evidence) {
    if (!e.document_id) continue;
    const label = e.evidence_label
      ? `${e.evidence_label}${e.page_number != null ? ` · p.${e.page_number}` : ""}`
      : e.page_number != null
        ? `Page ${e.page_number}`
        : "Source";
    add(e.document_id, e.page_number, label);
  }

  return out;
}

export function SourceDocumentLink({
  documentId,
  page,
  label,
  className,
  onClick,
}: SourceRef & {
  className?: string;
  onClick?: (e: MouseEvent) => void;
}) {
  return (
    <Link
      to={documentSourceHref(documentId, page)}
      className={clsx("ui-link font-medium", className)}
      onClick={onClick}
    >
      {label}
    </Link>
  );
}

export function SourceDocumentLinks({
  refs,
  className,
  prefix = "Source",
}: {
  refs: SourceRef[];
  className?: string;
  prefix?: string | null;
}) {
  if (refs.length === 0) return null;

  return (
    <p className={clsx("text-xs text-ink-soft leading-relaxed", className)}>
      {prefix && <span className="text-ink-mute">{prefix}: </span>}
      {refs.map((ref, i) => (
        <span key={`${ref.documentId}-${ref.page ?? "all"}`}>
          {i > 0 && <span className="text-line mx-1.5">·</span>}
          <SourceDocumentLink
            {...ref}
            onClick={(e) => e.stopPropagation()}
          />
        </span>
      ))}
    </p>
  );
}
