import { useCallback, type ReactNode } from "react";

import { useSortable, type SortState, type SortValue } from "../lib/useSortable";

export interface Column<T> {
  key: string;
  header: ReactNode;
  render: (row: T) => ReactNode;
  /** Present when the column can be sorted. */
  sortValue?: (row: T) => SortValue;
  align?: "left" | "right";
  title?: string;
  className?: string;
  /** Let long content wrap instead of keeping the cell on one line. */
  wrap?: boolean;
}

interface DataTableProps<T> {
  rows: readonly T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  initialSort?: SortState;
  onRowClick?: (row: T) => void;
  selectedKey?: string | null;
  caption?: string;
  dense?: boolean;
}

export function DataTable<T>({
  rows,
  columns,
  rowKey,
  initialSort,
  onRowClick,
  selectedKey,
  caption,
  dense = false,
}: DataTableProps<T>) {
  const getValue = useCallback(
    (row: T, key: string) => columns.find((column) => column.key === key)?.sortValue?.(row),
    [columns],
  );
  const { sorted, sort, toggle } = useSortable(rows, getValue, initialSort ?? null);
  const cell = dense ? "px-2.5 py-1.5" : "px-3 py-2";

  return (
    <div className="overflow-x-auto rounded-xl border border-line bg-panel">
      <table className="w-full border-collapse text-sm">
        {caption && <caption className="sr-only">{caption}</caption>}
        <thead>
          <tr className="border-b border-line text-xs text-muted">
            {columns.map((column) => {
              const active = sort?.key === column.key;
              const ariaSort = active ? (sort.direction === "asc" ? "ascending" : "descending") : undefined;
              const align = column.align === "right" ? "text-right" : "text-left";
              return (
                <th key={column.key} scope="col" aria-sort={ariaSort} title={column.title} className={`${cell} ${align} font-medium whitespace-nowrap`}>
                  {column.sortValue ? (
                    <button
                      type="button"
                      onClick={() => toggle(column.key)}
                      className={`inline-flex items-center gap-1 hover:text-fg ${active ? "text-fg" : ""}`}
                    >
                      {column.header}
                      <span aria-hidden className="text-[10px]">
                        {active ? (sort.direction === "asc" ? "▲" : "▼") : ""}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => {
            const key = rowKey(row);
            const selected = key === selectedKey;
            return (
              <tr
                key={key}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                onKeyDown={
                  onRowClick
                    ? (event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          onRowClick(row);
                        }
                      }
                    : undefined
                }
                tabIndex={onRowClick ? 0 : undefined}
                aria-selected={onRowClick ? selected : undefined}
                className={`border-b border-line last:border-0 ${onRowClick ? "cursor-pointer hover:bg-panel-2" : ""} ${selected ? "bg-panel-2" : ""}`}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={`${cell} ${column.align === "right" ? "num text-right" : ""} ${column.className ?? ""} ${column.wrap ? "whitespace-normal" : "whitespace-nowrap"}`}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
