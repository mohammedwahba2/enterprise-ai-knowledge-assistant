import type { PageInfo } from "./api";

/** Visual tone of a document status: busy (in progress), ok, partial (usable but incomplete), bad. */
export type Tone = "busy" | "ok" | "partial" | "bad";

const TONES: Record<string, Tone> = {
  uploaded: "busy",
  parsing: "busy",
  chunking: "busy",
  embedding: "busy",
  ready: "ok",
  ready_partial: "partial",
  unsupported_scanned: "bad",
  unsupported_garbled: "bad",
  failed: "bad",
};

export const PROCESSING = ["uploaded", "parsing", "chunking", "embedding"] as const;
export const NEEDS_ATTENTION = ["failed", "unsupported_scanned", "unsupported_garbled", "ready_partial"] as const;

export const toneOf = (status: string): Tone => TONES[status] ?? "busy";
export const isProcessing = (status: string) => (PROCESSING as readonly string[]).includes(status);
export const needsAttention = (status: string) => (NEEDS_ATTENTION as readonly string[]).includes(status);

/** Error codes the API can attach to a document; each has a message under `Library.reason`. */
export const REASON_CODES = [
  "ENCRYPTED",
  "CORRUPT",
  "CONVERSION_FAILED",
  "EMPTY_DOCUMENT",
  "TOO_MANY_PAGES",
  "NO_TEXT_LAYER",
  "GARBLED_TEXT",
  "PARTIAL_TEXT",
  "PROCESSING_ERROR",
  "PROCESSING_CRASHED",
  "FILE_MISSING",
  "STORAGE_UNAVAILABLE",
  "EMBEDDER_UNAVAILABLE",
  "EMBEDDING_FAILED",
] as const;

export const isReasonCode = (code: string | null): code is (typeof REASON_CODES)[number] =>
  code !== null && (REASON_CODES as readonly string[]).includes(code);

export type PageRange = { from: number; to: number };

/** Collapse the page numbers whose text could not be used into contiguous ranges. */
export function unreadableRanges(pages: PageInfo[]): PageRange[] {
  const bad = pages
    .filter((p) => p.extraction_state !== "text")
    .map((p) => p.page_number)
    .sort((a, b) => a - b);
  const ranges: PageRange[] = [];
  for (const n of bad) {
    const last = ranges[ranges.length - 1];
    if (last && n === last.to + 1) last.to = n;
    else ranges.push({ from: n, to: n });
  }
  return ranges;
}

/** "41–52, 60" with Western digits regardless of locale (the approved default). */
export const formatRanges = (ranges: PageRange[]): string =>
  ranges.map((r) => (r.from === r.to ? String(r.from) : `${r.from}–${r.to}`)).join(", ");
