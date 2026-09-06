/**
 * Tiny CSV exporter — no dependency.
 *
 * RFC 4180 quoting (only when needed): cells containing comma, double-quote,
 * or newline are wrapped in double-quotes; embedded quotes are doubled.
 * `downloadCSV` creates an object URL and triggers a click on a hidden <a>;
 * jsdom polyfills createObjectURL/URL.revokeObjectURL but not anchor.click()
 * side-effects on the DOM, so tests stub the anchor (see admin-anticheat
 * tests).
 */

export function csvEscape(value: string | number): string {
  const s = String(value);
  if (/[",\n\r]/.test(s)) {
    return `"${s.replace(/"/g, '""')}"`;
  }
  return s;
}

export function toCSV(rows: (string | number)[][]): string {
  return rows.map((row) => row.map(csvEscape).join(",")).join("\r\n");
}

/** Trigger a CSV file download in the browser. */
export function downloadCSV(filename: string, content: string): void {
  const blob = new Blob([content], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.rel = "noopener";
  document.body.appendChild(anchor);
  anchor.click();
  document.body.removeChild(anchor);
  URL.revokeObjectURL(url);
}
