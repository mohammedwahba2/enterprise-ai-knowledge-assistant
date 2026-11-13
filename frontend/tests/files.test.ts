import { describe, expect, it } from "vitest";
import { MAX_UPLOAD_BYTES, formatBytes, preflight } from "@/lib/files";

const units = { b: "B", kb: "KB", mb: "MB", gb: "GB" };
const arUnits = { b: "بايت", kb: "ك.ب", mb: "م.ب", gb: "ج.ب" };

describe("preflight", () => {
  it("accepts the supported types regardless of case", () => {
    for (const name of ["a.pdf", "A.PDF", "x.docx", "x.pptx", "n.txt", "r.md", "r.markdown"]) {
      expect(preflight({ name, size: 10 })).toBeNull();
    }
  });
  it("rejects other types, extensionless names, empty and oversized files", () => {
    expect(preflight({ name: "x.exe", size: 10 })).toBe("TYPE_CLIENT");
    expect(preflight({ name: "x.html", size: 10 })).toBe("TYPE_CLIENT");
    expect(preflight({ name: "noext", size: 10 })).toBe("TYPE_CLIENT");
    expect(preflight({ name: "a.pdf", size: 0 })).toBe("EMPTY_FILE");
    expect(preflight({ name: "a.pdf", size: MAX_UPLOAD_BYTES + 1 })).toBe("TOO_LARGE_CLIENT");
    expect(preflight({ name: "a.pdf", size: MAX_UPLOAD_BYTES })).toBeNull();
  });
});

describe("formatBytes", () => {
  it("scales units", () => {
    expect(formatBytes(0, "en", units)).toBe("0 B");
    expect(formatBytes(1023, "en", units)).toBe("1,023 B");
    expect(formatBytes(1536, "en", units)).toBe("1.5 KB");
    expect(formatBytes(5 * 1024 * 1024, "en", units)).toBe("5 MB");
    expect(formatBytes(50 * 1024 * 1024, "en", units)).toBe("50 MB");
    expect(formatBytes(3 * 1024 ** 3, "en", units)).toBe("3 GB");
  });
  it("uses Western digits in Arabic, with Arabic unit labels", () => {
    const text = formatBytes(2.5 * 1024 * 1024, "ar", arUnits);
    expect(text).toMatch(/^2[.٫]5 م\.ب$/);
    expect(text).not.toMatch(/[٠-٩]/);
    expect(formatBytes(12 * 1024 * 1024, "ar", arUnits)).not.toMatch(/[٠-٩]/);
  });
});
