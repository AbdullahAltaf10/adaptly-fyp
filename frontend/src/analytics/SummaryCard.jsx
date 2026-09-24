import { NOT_AVAILABLE } from "./format";

/**
 * One reusable stat tile: a label and an already-formatted value.
 *
 * Formatting (including the "Not available" fallback for missing data)
 * happens in the caller via `src/analytics/format.js`, so this component
 * stays a plain, easily-testable presentational box.
 */
export default function SummaryCard({ label, value, description }) {
  const isUnavailable = value === NOT_AVAILABLE;

  return (
    <div
      role="group"
      aria-label={label}
      style={{
        border: "1px solid #ddd",
        borderRadius: "8px",
        padding: "0.9rem 1rem",
        minWidth: "160px",
        background: "#fff",
      }}
    >
      <p style={{ margin: 0, fontSize: "0.85rem", color: "#555" }}>{label}</p>
      <p
        style={{
          margin: "0.3rem 0 0",
          fontSize: "1.4rem",
          fontWeight: 600,
          color: isUnavailable ? "#777" : "#1a1a1a",
        }}
      >
        {value}
      </p>
      {description && (
        <p style={{ margin: "0.3rem 0 0", fontSize: "0.8rem", color: "#666" }}>
          {description}
        </p>
      )}
    </div>
  );
}
