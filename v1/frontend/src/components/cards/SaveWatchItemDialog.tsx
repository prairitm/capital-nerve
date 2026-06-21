import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X } from "lucide-react";
import { api } from "@/api/client";

interface Props {
  open: boolean;
  onClose: () => void;
  companyId: number | null;
  defaultTitle: string;
  defaultDescription?: string;
  cardId?: number | null;
}

export function SaveWatchItemDialog({
  open,
  onClose,
  companyId,
  defaultTitle,
  defaultDescription,
  cardId,
}: Props) {
  const [title, setTitle] = useState(defaultTitle);
  const [description, setDescription] = useState(defaultDescription || "");
  const [target, setTarget] = useState<string>("");
  const [operator, setOperator] = useState<string>("<");

  const qc = useQueryClient();

  useEffect(() => {
    setTitle(defaultTitle);
    setDescription(defaultDescription || "");
  }, [defaultTitle, defaultDescription]);

  const create = useMutation({
    mutationFn: async () => {
      return api("/watch-items", {
        method: "POST",
        body: {
          company_id: companyId,
          card_id: cardId ?? null,
          title,
          description,
          target_value: target ? Number(target) : null,
          condition_operator: operator,
          condition_json: {},
        },
      });
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["watchItems"] });
      onClose();
    },
  });

  if (!open) return null;
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/60 backdrop-blur-sm" onClick={onClose} />
      <div className="relative w-full max-w-md card p-5">
        <div className="flex items-start justify-between mb-3">
          <div>
            <div className="text-[11px] uppercase tracking-wider text-ink-soft">Watch Item</div>
            <h3 className="text-lg font-semibold">Save what to monitor</h3>
          </div>
          <button onClick={onClose} className="btn-ghost p-1.5">
            <X size={16} />
          </button>
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-xs text-ink-mute mb-1 block">Title</label>
            <input value={title} onChange={(e) => setTitle(e.target.value)} className="input" />
          </div>
          <div>
            <label className="text-xs text-ink-mute mb-1 block">Why does this matter?</label>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              rows={3}
              className="input"
              placeholder="Need margin recovery for thesis to remain intact…"
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-xs text-ink-mute mb-1 block">Notify if value is</label>
              <select value={operator} onChange={(e) => setOperator(e.target.value)} className="input">
                <option value="<">below</option>
                <option value=">">above</option>
                <option value="<=">at or below</option>
                <option value=">=">at or above</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-ink-mute mb-1 block">Threshold</label>
              <input
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                className="input"
                placeholder="16"
              />
            </div>
          </div>
        </div>
        <div className="mt-4 flex justify-end gap-2">
          <button onClick={onClose} className="btn-secondary">
            Cancel
          </button>
          <button
            onClick={() => create.mutate()}
            disabled={!companyId || !title || create.isPending}
            className="btn-primary"
          >
            {create.isPending ? "Saving…" : "Save"}
          </button>
        </div>
        {create.isError && (
          <p className="mt-2 text-xs text-negative">Failed to save. Try again.</p>
        )}
      </div>
    </div>
  );
}
