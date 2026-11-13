import { formatNumber, type Locale } from "@/i18n/locales";

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024; // mirrors the server limit; the server is authoritative
export const ACCEPTED_EXTENSIONS = ["pdf", "docx", "pptx", "txt", "md", "markdown"] as const;
export const ACCEPT_ATTR = ACCEPTED_EXTENSIONS.map((e) => `.${e}`).join(",");

export type ClientReject = "TYPE_CLIENT" | "TOO_LARGE_CLIENT" | "EMPTY_FILE";

/** Cheap pre-flight so people get instant feedback; the server re-validates by content. */
export function preflight(file: { name: string; size: number }): ClientReject | null {
  const ext = file.name.includes(".") ? file.name.split(".").pop()!.toLowerCase() : "";
  if (!(ACCEPTED_EXTENSIONS as readonly string[]).includes(ext)) return "TYPE_CLIENT";
  if (file.size === 0) return "EMPTY_FILE";
  if (file.size > MAX_UPLOAD_BYTES) return "TOO_LARGE_CLIENT";
  return null;
}

export type Units = { b: string; kb: string; mb: string; gb: string };

/** Human-readable size with Western digits in every language (decision D11). */
export function formatBytes(bytes: number, locale: Locale, units: Units): string {
  const steps: [number, string][] = [
    [1024 ** 3, units.gb],
    [1024 ** 2, units.mb],
    [1024, units.kb],
  ];
  for (const [size, unit] of steps) {
    if (bytes >= size) {
      const value = bytes / size;
      return `${formatNumber(value, locale, { maximumFractionDigits: value < 10 ? 1 : 0 })} ${unit}`;
    }
  }
  return `${formatNumber(bytes, locale)} ${units.b}`;
}
