import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import clsx from "clsx";

export interface FilterOption<T extends string = string> {
  value: T;
  label: string;
}

interface Props<T extends string> {
  label: string;
  value: T;
  options: FilterOption<T>[];
  onChange: (value: T) => void;
  className?: string;
}

export function ColumnHeaderFilter<T extends string>({
  label,
  value,
  options,
  onChange,
  className,
}: Props<T>) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLTableHeaderCellElement>(null);
  const listId = useId();
  const active = value !== "";
  const selected = options.find((o) => o.value === value);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <th ref={rootRef} className={clsx("relative px-5 py-2 text-left align-bottom", className)}>
      <button
        type="button"
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={listId}
        onClick={() => setOpen((v) => !v)}
        className={clsx(
          "inline-flex items-center gap-1 rounded-md px-1 -mx-1 py-0.5 text-[11px] font-medium uppercase tracking-wider transition-colors",
          active ? "text-ink bg-surface-2/80" : "text-ink-soft hover:text-ink hover:bg-surface-2/40",
        )}
      >
        <span>{active && selected ? selected.label : label}</span>
        <ChevronDown size={12} className={clsx("shrink-0 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div
          id={listId}
          role="listbox"
          className="absolute left-3 top-full z-30 mt-1 min-w-[11rem] max-h-64 overflow-y-auto rounded-xl border border-line bg-surface shadow-card py-1"
        >
          {options.map((opt) => (
            <button
              key={opt.value || "__all__"}
              type="button"
              role="option"
              aria-selected={value === opt.value}
              onClick={() => {
                onChange(opt.value);
                setOpen(false);
              }}
              className={clsx(
                "w-full text-left px-3 py-1.5 text-xs transition-colors",
                value === opt.value
                  ? "text-ink bg-surface-2 font-medium"
                  : "text-ink-mute hover:bg-surface-2/60 hover:text-ink",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}
    </th>
  );
}

/** Compact select for mobile filter bar — same options, less chrome. */
export function CompactFilterSelect<T extends string>({
  label,
  value,
  options,
  onChange,
}: Omit<Props<T>, "className">) {
  const active = value !== "";

  return (
    <label className="inline-flex items-center gap-1.5 text-xs text-ink-mute">
      <span className="sr-only">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as T)}
        aria-label={label}
        className={clsx(
          "rounded-lg border px-2 py-1.5 text-xs outline-none focus:border-line-strong",
          active
            ? "border-line-strong bg-surface-2 text-ink"
            : "border-line/60 bg-surface-2/40 text-ink-mute",
        )}
      >
        {options.map((opt) => (
          <option key={opt.value || "__all__"} value={opt.value}>
            {opt.value === "" ? label : opt.label}
          </option>
        ))}
      </select>
    </label>
  );
}
