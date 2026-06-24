import { Link } from "react-router-dom";
import type { ExtractedValue } from "@/api/types";
import { documentSourceHref } from "@/lib/documentSource";

export function FactSourceLink({
  documentId,
  fact,
}: {
  documentId: string | null;
  fact: Pick<ExtractedValue, "source_text" | "source_page">;
}) {
  if (!fact.source_text) return null;
  if (documentId) {
    return (
      <Link
        to={documentSourceHref(documentId, {
          page: fact.source_page,
          highlight: fact.source_text,
        })}
        className="ui-link hover:underline block"
        title="View in source document"
      >
        {fact.source_text}
      </Link>
    );
  }
  return <span>{fact.source_text}</span>;
}
