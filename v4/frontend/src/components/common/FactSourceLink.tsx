import { Link } from "react-router-dom";
import { FileSearch } from "lucide-react";
import type { ExtractedValue } from "@/api/types";
import { documentSourceHref } from "@/lib/documentSource";

export function FactSourceLink({
  documentId,
  fact,
}: {
  documentId: string | null;
  fact: Pick<
    ExtractedValue,
    "source_text" | "source_page" | "value_numeric" | "value_text" | "basis"
  >;
}) {
  if (!fact.source_text) return null;
  if (documentId) {
    const highlightValue = fact.value_numeric ?? fact.value_text;
    const label =
      fact.source_page != null
        ? `View source on page ${fact.source_page}`
        : "View source document";

    return (
      <Link
        to={documentSourceHref(documentId, {
          page: fact.source_page,
          highlight: fact.source_text,
          value: highlightValue,
          context: fact.basis,
        })}
        className="ui-link inline-flex size-8 shrink-0 items-center justify-center rounded-lg border border-line/70 bg-surface-2 hover:border-line-strong hover:bg-surface-3"
        title={label}
        aria-label={label}
      >
        <FileSearch size={15} aria-hidden="true" />
        <span className="sr-only">{label}</span>
      </Link>
    );
  }
  return null;
}
