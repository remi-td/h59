import type { FreshnessClass } from "../api/types";

const LABELS: Record<FreshnessClass, string> = {
  fresh: "Fresh",
  partial: "Partial",
  stale: "Stale",
  empty: "Empty",
  error: "Error",
};

export function DataQualityBadge({ status }: { status: FreshnessClass }) {
  return <span className={`quality-badge quality-${status}`}>{LABELS[status]}</span>;
}
