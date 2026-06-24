import type { SeverityLevel, SignalDirection } from "@/api/types";
import type { FilterOption } from "@/components/common/ColumnHeaderFilter";

export const SIGNAL_CATEGORY_FILTERS: FilterOption[] = [
  { value: "", label: "All categories" },
  { value: "growth", label: "Growth" },
  { value: "margin", label: "Margin" },
  { value: "earnings_quality", label: "Earnings Quality" },
  { value: "profit_quality", label: "Profit Quality" },
  { value: "cash_quality", label: "Cash Quality" },
  { value: "expense", label: "Expense" },
  { value: "debt", label: "Debt" },
];

export const SIGNAL_SEVERITY_FILTERS: FilterOption<SeverityLevel | "">[] = [
  { value: "", label: "Any materiality" },
  { value: "LOW", label: "Routine" },
  { value: "MEDIUM", label: "Notable" },
  { value: "HIGH", label: "Material" },
  { value: "CRITICAL", label: "Market-moving" },
];

export const SIGNAL_DIRECTION_FILTERS: FilterOption<SignalDirection | "">[] = [
  { value: "", label: "Any direction" },
  { value: "POSITIVE", label: "Positive" },
  { value: "NEGATIVE", label: "Negative" },
  { value: "MIXED", label: "Mixed" },
];

export interface SignalTableFilters {
  category: string;
  severity: string;
  direction: string;
  onCategoryChange: (value: string) => void;
  onSeverityChange: (value: string) => void;
  onDirectionChange: (value: string) => void;
  onClear: () => void;
}

export function signalFiltersActive(filters: Pick<SignalTableFilters, "category" | "severity" | "direction">) {
  return Boolean(filters.category || filters.severity || filters.direction);
}
