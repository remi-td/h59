import type { TrustClass } from "../api/types";

const LABELS: Record<TrustClass, string> = {
  measured: "Measured",
  derived: "Derived",
  estimated: "Estimated",
  vendor_score: "Vendor score",
  unknown: "Unknown",
};

export function TrustBadge({ trustClass }: { trustClass: TrustClass }) {
  return <span className={`trust-badge trust-${trustClass}`}>{LABELS[trustClass]}</span>;
}
