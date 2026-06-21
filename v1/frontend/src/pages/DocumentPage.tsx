import { useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { BackButton } from "@/components/common/BackButton";
import { api } from "@/api/client";
import type { DocumentDetail } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { EvidenceViewer } from "@/components/evidence/EvidenceViewer";

const ACTIVE_EXTRACTION = new Set(["PENDING", "PROCESSING"]);

export function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const queryClient = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api<DocumentDetail>(`/documents/${documentId}`),
    enabled: !!documentId,
    refetchInterval: (query) =>
      ACTIVE_EXTRACTION.has(query.state.data?.extraction_status ?? "") ? 2500 : false,
  });

  const reextract = useMutation({
    mutationFn: () =>
      api<{ queued: boolean; job_id: number }>(`/documents/${documentId}/reextract`, {
        method: "POST",
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["document", documentId] });
    },
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Document not found.</div>;

  const extractionBusy = ACTIVE_EXTRACTION.has(data.extraction_status);
  const canReextract = data.has_source_file && !extractionBusy && !reextract.isPending;

  return (
    <div className="space-y-4">
      <BackButton
        fallback={
          data.company?.symbol ? `/company/${data.company.symbol}` : "/"
        }
      />
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <div className="text-[11px] uppercase tracking-wider text-ink-soft">
            {data.document_type.replace(/_/g, " ")}
          </div>
          <h1 className="text-xl md:text-2xl font-semibold">{data.document_title}</h1>
          {data.company && (
            <p className="text-sm text-ink-mute">
              {data.company.company_name}
              {data.company.symbol ? ` · ${data.company.symbol}` : ""}
            </p>
          )}
          {extractionBusy && (
            <p className="text-xs text-ink-mute mt-2">Re-extracting this filing…</p>
          )}
          {reextract.isError && (
            <p className="text-xs text-negative mt-2">
              {reextract.error instanceof Error ? reextract.error.message : "Re-extract failed"}
            </p>
          )}
        </div>
        {data.has_source_file && (
          <button
            type="button"
            className="btn-secondary text-sm shrink-0 self-start"
            disabled={!canReextract}
            onClick={() => reextract.mutate()}
          >
            <RefreshCw size={14} className={reextract.isPending || extractionBusy ? "animate-spin" : ""} />
            {extractionBusy ? "Re-extracting…" : "Re-extract file"}
          </button>
        )}
      </div>
      <EvidenceViewer doc={data} />
    </div>
  );
}
