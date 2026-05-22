import { useNavigate, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { api } from "@/api/client";
import type { DocumentDetail } from "@/api/types";
import { PageLoader } from "@/components/common/Spinner";
import { EvidenceViewer } from "@/components/evidence/EvidenceViewer";

export function DocumentPage() {
  const { documentId } = useParams<{ documentId: string }>();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["document", documentId],
    queryFn: () => api<DocumentDetail>(`/documents/${documentId}`),
    enabled: !!documentId,
  });

  if (isLoading) return <PageLoader />;
  if (!data) return <div className="text-ink-mute">Document not found.</div>;

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="btn-ghost -ml-2 text-sm">
        <ArrowLeft size={16} /> Back
      </button>
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
      </div>
      <EvidenceViewer doc={data} />
    </div>
  );
}
