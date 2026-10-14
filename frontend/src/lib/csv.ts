export type CsvRow = Record<string, string | number | boolean | null | undefined>;

function escape(value: CsvRow[string]): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  return /[",\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(rows: CsvRow[]): string {
  const first = rows[0];
  if (!first) return "";
  const headers = Object.keys(first);
  const lines = rows.map((row) => headers.map((header) => escape(row[header])).join(","));
  return [headers.join(","), ...lines].join("\n");
}

export function downloadCsv(filename: string, rows: CsvRow[]): void {
  downloadFile(filename, toCsv(rows), "text/csv;charset=utf-8");
}

/** Save text as a file through the browser's download. */
export function downloadFile(filename: string, content: string, type: string): void {
  const blob = new Blob([content], { type });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
