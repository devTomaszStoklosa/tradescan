/** Small presentational building blocks shared by every page. */
import type { ComponentProps, CSSProperties, InputHTMLAttributes, ReactNode, SelectHTMLAttributes } from "react";

import type { Direction } from "../api/client";

const cx = (...classes: (string | false | null | undefined)[]) => classes.filter(Boolean).join(" ");

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: string; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Panel({ children, className }: { children: ReactNode; className?: string }) {
  return <section className={cx("rounded-xl border border-line bg-panel p-4", className)}>{children}</section>;
}

type ButtonVariant = "primary" | "secondary" | "ghost";

export function Button({
  variant = "secondary",
  className,
  ...props
}: ComponentProps<"button"> & { variant?: ButtonVariant }) {
  const styles: Record<ButtonVariant, string> = {
    primary: "bg-accent text-accent-fg hover:opacity-90",
    secondary: "border border-line bg-panel hover:bg-panel-2",
    ghost: "hover:bg-panel-2",
  };
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition disabled:cursor-not-allowed disabled:opacity-50",
        styles[variant],
        className,
      )}
      {...props}
    />
  );
}

export function Field({ label, children, hint }: { label: string; children: ReactNode; hint?: string }) {
  return (
    <label className="flex min-w-0 flex-col gap-1 text-xs font-medium text-muted">
      <span>{label}</span>
      {children}
      {hint && <span className="font-normal">{hint}</span>}
    </label>
  );
}

const control =
  "h-9 w-full min-w-0 rounded-lg border border-line bg-panel px-2.5 text-sm text-fg placeholder:text-muted focus:border-accent focus:outline-none";

export function Input({ className, ...props }: InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(control, className)} {...props} />;
}

export function Select({ className, ...props }: SelectHTMLAttributes<HTMLSelectElement>) {
  return <select className={cx(control, className)} {...props} />;
}

/** Number input bound to `number | null`; empty means "server default". */
export function NumberInput({
  value,
  onChange,
  placeholder,
  step = "any",
  min,
  max,
  label,
  id,
  invalid,
  className,
}: {
  value: number | null;
  onChange: (value: number | null) => void;
  placeholder?: string;
  step?: string;
  min?: number;
  max?: number;
  label?: string;
  id?: string;
  invalid?: boolean;
  className?: string;
}) {
  return (
    <Input
      type="number"
      inputMode="decimal"
      id={id}
      step={step}
      min={min}
      max={max}
      aria-label={label}
      aria-invalid={invalid || undefined}
      className={cx(invalid && "ring-2 ring-down/60", className)}
      placeholder={placeholder}
      value={value ?? ""}
      onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))}
    />
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex h-9 rounded-lg border border-line bg-panel p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="radio"
          aria-checked={value === option.value}
          onClick={() => onChange(option.value)}
          className={cx(
            "rounded-md px-3 text-sm transition",
            value === option.value ? "bg-panel-2 font-medium text-fg shadow-sm" : "text-muted hover:text-fg",
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

export function ToggleChip({
  active,
  onClick,
  children,
  color,
}: {
  active: boolean;
  onClick: () => void;
  children: ReactNode;
  color?: string;
}) {
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      style={color ? ({ "--chip": color } as CSSProperties) : undefined}
      className={cx(
        "rounded-full border px-2.5 py-1 text-xs font-medium transition",
        active ? "chip" : "border-line text-muted hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}

export function DirectionBadge({ direction }: { direction: Direction }) {
  const long = direction === "long";
  return (
    <span
      className={cx(
        "inline-flex rounded-md px-1.5 py-0.5 text-xs font-semibold uppercase",
        long ? "bg-up/15 text-up" : "bg-down/15 text-down",
      )}
    >
      {long ? "Long" : "Short"}
    </span>
  );
}

export function StatTile({ label, value, sub, valueClass }: { label: string; value: ReactNode; sub?: ReactNode; valueClass?: string }) {
  return (
    <div className="rounded-xl border border-line bg-panel px-3 py-2.5">
      <div className="text-xs text-muted">{label}</div>
      <div className={cx("num mt-0.5 text-lg font-semibold", valueClass)}>{value}</div>
      {sub && <div className="num text-xs text-muted">{sub}</div>}
    </div>
  );
}

export function Loading({ message }: { message: string }) {
  return (
    <Panel className="flex items-center gap-3 text-sm text-muted">
      <span className="size-4 animate-spin rounded-full border-2 border-line border-t-accent" aria-hidden />
      <span role="status">{message}</span>
    </Panel>
  );
}

export function ErrorBox({ error, onRetry }: { error: unknown; onRetry?: () => void }) {
  const message = error instanceof Error ? error.message : String(error);
  return (
    <Panel className="flex flex-wrap items-center justify-between gap-3 border-down/40 bg-down/5">
      <p role="alert" className="text-sm text-down">
        {message}
      </p>
      {onRetry && <Button onClick={onRetry}>Retry</Button>}
    </Panel>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <Panel className="py-10 text-center">
      <p className="font-medium">{title}</p>
      {children && <div className="mt-1 text-sm text-muted">{children}</div>}
    </Panel>
  );
}

export function Notice({ children }: { children: ReactNode }) {
  return <p className="rounded-lg border border-warn/30 bg-warn/10 px-3 py-2 text-sm text-warn">{children}</p>;
}
