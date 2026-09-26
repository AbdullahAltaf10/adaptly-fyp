/**
 * The small set of UI primitives every screen is built from.
 *
 * Styling is Tailwind, using the theme in `src/index.css` — no hex codes here,
 * so the look is changed by editing that one `@theme` block. Deliberately
 * generic: this is scaffolding for a real design, not the design.
 *
 * The parts that are NOT cosmetic, and should survive a redesign:
 *
 * - **A field's error is tied to its input** via `aria-describedby` and
 *   `aria-invalid`. A red border alone tells a screen-reader user nothing.
 * - **Alerts announce themselves.** An error that appears silently after a
 *   failed submit is invisible to anyone not looking at that part of the page.
 * - **A busy button keeps its place.** Swapping a label for a narrower spinner
 *   makes the page jump under the cursor.
 * - **Touch targets stay at least 2.5rem tall.** In `rem`, so they grow with
 *   the learner's font-size setting instead of staying small.
 */

import { useId } from "react";

/* ------------------------------------------------------------------ Button */

const BUTTON_VARIANTS = {
  primary: "bg-accent text-on-accent border-accent hover:bg-accent-hover",
  secondary: "bg-surface text-ink border-line-strong hover:bg-page",
  quiet: "bg-transparent text-accent border-transparent hover:underline",
  danger: "bg-danger text-inverse border-danger hover:opacity-90",
};

export function Button({
  variant = "primary",
  busy = false,
  busyLabel = "Working...",
  disabled,
  className = "",
  children,
  ...rest
}) {
  return (
    <button
      // A busy button must not be re-submittable, but `aria-busy` is what tells
      // assistive technology *why* it is disabled.
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={[
        "inline-flex items-center justify-center min-h-10 px-4 py-2",
        "rounded-md border font-medium transition-colors",
        "disabled:cursor-not-allowed disabled:opacity-60",
        BUTTON_VARIANTS[variant] ?? BUTTON_VARIANTS.primary,
        className,
      ].join(" ")}
      {...rest}
    >
      {busy ? busyLabel : children}
    </button>
  );
}

/* ------------------------------------------------------------------- Field */

/**
 * A labelled control with optional hint and error.
 *
 * `children` may be a render function, which receives the `id` and the ARIA
 * attributes already wired up — that is what stops each form inventing its own
 * way of connecting a message to an input.
 */
export function Field({ label, error, hint, required = false, children, id: providedId }) {
  const generated = useId();
  const id = providedId ?? generated;
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;

  const aria = {
    id,
    "aria-invalid": error ? true : undefined,
    "aria-describedby": [hintId, errorId].filter(Boolean).join(" ") || undefined,
  };

  return (
    <div className="mb-4">
      <label htmlFor={id} className="block mb-1 font-medium">
        {label}
        {required && (
          <>
            <span aria-hidden="true" className="text-danger"> *</span>
            <ScreenReaderOnly> (required)</ScreenReaderOnly>
          </>
        )}
      </label>

      {hint && (
        <p id={hintId} className="mt-0 mb-1 text-sm text-muted">
          {hint}
        </p>
      )}

      {typeof children === "function" ? children(aria) : children}

      {error && (
        <p id={errorId} className="mt-1 mb-0 text-sm text-danger">
          {error}
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------- Input / Select / Textarea */

const CONTROL_BASE =
  "w-full box-border min-h-10 px-3 py-2 rounded-md border bg-surface text-ink " +
  "placeholder:text-muted disabled:opacity-60 disabled:cursor-not-allowed";

const borderFor = (invalid) => (invalid ? "border-danger" : "border-line");

export function Input({ invalid, className = "", ...rest }) {
  return <input className={[CONTROL_BASE, borderFor(invalid), className].join(" ")} {...rest} />;
}

export function Select({ invalid, className = "", children, ...rest }) {
  return (
    <select className={[CONTROL_BASE, borderFor(invalid), className].join(" ")} {...rest}>
      {children}
    </select>
  );
}

export function Textarea({ invalid, className = "", ...rest }) {
  return (
    <textarea
      className={[CONTROL_BASE, borderFor(invalid), "min-h-32 resize-y", className].join(" ")}
      {...rest}
    />
  );
}

/* ------------------------------------------------------------------- Alert */

const ALERT_TONES = {
  error: "border-danger bg-danger-soft",
  success: "border-success bg-success-soft",
  warning: "border-warning bg-warning-soft",
  info: "border-info bg-info-soft",
};

const ALERT_TITLE_TONES = {
  error: "text-danger",
  success: "text-success",
  warning: "text-warning",
  info: "text-info",
};

/**
 * `tone="error"` announces assertively; everything else is polite.
 *
 * An error blocking the learner is worth interrupting for. A success message
 * is not — interrupting for those trains people to ignore the announcements
 * that do matter.
 */
export function Alert({ tone = "info", title, children, className = "" }) {
  return (
    <div
      role={tone === "error" ? "alert" : "status"}
      aria-live={tone === "error" ? "assertive" : "polite"}
      className={[
        "border rounded-md p-3 mb-4 text-ink",
        ALERT_TONES[tone] ?? ALERT_TONES.info,
        className,
      ].join(" ")}
    >
      {title && (
        <strong className={["block mb-1", ALERT_TITLE_TONES[tone] ?? ALERT_TITLE_TONES.info].join(" ")}>
          {title}
        </strong>
      )}
      <div>{children}</div>
    </div>
  );
}

/* -------------------------------------------------------------------- Card */

export function Card({ title, subtitle, children, footer, className = "", as: Tag = "section" }) {
  return (
    <Tag className={["border border-line rounded-md bg-surface p-6", className].join(" ")}>
      {title && <h2 className="mt-0 mb-1 text-xl font-semibold">{title}</h2>}
      {subtitle && <p className="mt-0 mb-4 text-muted">{subtitle}</p>}
      {children}
      {footer && <div className="mt-4">{footer}</div>}
    </Tag>
  );
}

/* ------------------------------------------------------------------ Layout */

/** Centred column for the signed-out screens. */
export function CenteredPage({ children, className = "" }) {
  return (
    <main className="min-h-screen flex items-center justify-center bg-page p-6">
      <div className={["w-full max-w-md", className].join(" ")}>{children}</div>
    </main>
  );
}

export function Spinner({ label = "Loading..." }) {
  return (
    <p role="status" aria-live="polite" className="text-muted">
      {label}
    </p>
  );
}

/** Visually hidden but read aloud — for labels a sighted user gets from layout. */
export function ScreenReaderOnly({ children }) {
  return <span className="sr-only">{children}</span>;
}
