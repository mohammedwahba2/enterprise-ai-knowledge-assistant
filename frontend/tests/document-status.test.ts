import { describe, expect, it } from "vitest";
import en from "@/messages/en.json";
import ar from "@/messages/ar.json";
import type { PageInfo } from "@/lib/api";
import { documents } from "@/lib/api";
import {
  formatRanges,
  isProcessing,
  needsAttention,
  NEEDS_ATTENTION,
  PROCESSING,
  REASON_CODES,
  toneOf,
  unreadableRanges,
} from "@/lib/documentStatus";

const page = (n: number, state: PageInfo["extraction_state"] = "text"): PageInfo => ({
  page_number: n,
  extraction_state: state,
  char_count: state === "text" ? 100 : 0,
});

const STATUSES = ["uploaded", "parsing", "chunking", "ready", "ready_partial", "unsupported_scanned", "unsupported_garbled", "failed"];

describe("unreadable page ranges", () => {
  it("collapses consecutive unusable pages into ranges", () => {
    const pages = [1, 2, 3, 4, 5, 6, 7, 8].map((n) => page(n, [3, 4, 5, 8].includes(n) ? "garbled" : "text"));
    expect(unreadableRanges(pages)).toEqual([
      { from: 3, to: 5 },
      { from: 8, to: 8 },
    ]);
  });
  it("treats image-only and garbled pages alike and ignores order", () => {
    const ranges = unreadableRanges([page(5, "image_only"), page(4, "garbled"), page(1)]);
    expect(ranges).toEqual([{ from: 4, to: 5 }]);
  });
  it("is empty when every page is readable", () => {
    expect(unreadableRanges([page(1), page(2)])).toEqual([]);
  });
  it("formats ranges with Western digits and an en dash", () => {
    expect(formatRanges([{ from: 41, to: 52 }, { from: 60, to: 60 }])).toBe("41–52, 60");
  });
});

describe("status classification", () => {
  it("only processing statuses are in flight", () => {
    for (const s of PROCESSING) expect(isProcessing(s)).toBe(true);
    for (const s of ["ready", "ready_partial", "failed", "unsupported_scanned", "unsupported_garbled"]) {
      expect(isProcessing(s)).toBe(false);
    }
  });
  it("matches the backend's needs-attention set", () => {
    expect([...NEEDS_ATTENTION].sort()).toEqual(["failed", "ready_partial", "unsupported_garbled", "unsupported_scanned"]);
    expect(needsAttention("ready")).toBe(false);
    expect(needsAttention("parsing")).toBe(false);
  });
  it("gives every status a tone, and unknown ones a safe default", () => {
    expect(toneOf("ready")).toBe("ok");
    expect(toneOf("ready_partial")).toBe("partial");
    expect(toneOf("failed")).toBe("bad");
    expect(toneOf("parsing")).toBe("busy");
    expect(toneOf("something_new")).toBe("busy");
  });
});

describe("processing messages", () => {
  it.each([
    ["en", en],
    ["ar", ar],
  ])("%s has a label and a fallback reason for every status", (_name, m) => {
    for (const s of STATUSES) {
      expect(m.Library.status).toHaveProperty(s);
      expect(m.Library.reason.fallback).toHaveProperty(s);
    }
  });
  it.each([
    ["en", en],
    ["ar", ar],
  ])("%s explains every error code the API can return", (_name, m) => {
    for (const code of REASON_CODES) expect(m.Library.reason).toHaveProperty(code);
  });
});

describe("document API helpers", () => {
  it("builds same-origin URLs scoped to the workspace", () => {
    expect(documents.eventsUrl("org-1")).toBe("/api/v1/orgs/org-1/documents/events");
  });
});
