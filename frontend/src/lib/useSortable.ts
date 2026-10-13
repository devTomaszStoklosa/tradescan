import { useMemo, useState } from "react";

export type SortDirection = "asc" | "desc";
export type SortValue = number | string | null | undefined;

export interface SortState {
  key: string;
  direction: SortDirection;
}

/** Missing values always sort last, whatever the direction. */
export function compareValues(a: SortValue, b: SortValue, direction: SortDirection): number {
  const aMissing = a === null || a === undefined || (typeof a === "number" && Number.isNaN(a));
  const bMissing = b === null || b === undefined || (typeof b === "number" && Number.isNaN(b));
  if (aMissing || bMissing) return aMissing === bMissing ? 0 : aMissing ? 1 : -1;
  const order = typeof a === "number" && typeof b === "number" ? a - b : String(a).localeCompare(String(b));
  return direction === "asc" ? order : -order;
}

export function useSortable<T>(
  rows: readonly T[],
  getValue: (row: T, key: string) => SortValue,
  initial: SortState | null = null,
) {
  const [sort, setSort] = useState<SortState | null>(initial);

  const sorted = useMemo(() => {
    if (!sort) return [...rows];
    return [...rows].sort((a, b) => compareValues(getValue(a, sort.key), getValue(b, sort.key), sort.direction));
  }, [rows, sort, getValue]);

  /** First click sorts descending (biggest first, what traders usually want), the next flips it. */
  const toggle = (key: string) =>
    setSort((current) =>
      current?.key === key ? { key, direction: current.direction === "desc" ? "asc" : "desc" } : { key, direction: "desc" },
    );

  return { sorted, sort, toggle };
}
