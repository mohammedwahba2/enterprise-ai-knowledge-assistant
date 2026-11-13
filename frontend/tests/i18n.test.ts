import { describe, expect, it } from "vitest";
import en from "@/messages/en.json";
import ar from "@/messages/ar.json";
import { dirOf, formatDate, formatNumber, isLocale, locales } from "@/i18n/locales";

function keys(obj: Record<string, unknown>, prefix = ""): string[] {
  return Object.entries(obj).flatMap(([k, v]) =>
    typeof v === "object" && v !== null
      ? keys(v as Record<string, unknown>, `${prefix}${k}.`)
      : [`${prefix}${k}`],
  );
}

function leaves(obj: Record<string, unknown>): string[] {
  return Object.values(obj).flatMap((v) =>
    typeof v === "object" && v !== null ? leaves(v as Record<string, unknown>) : [String(v)],
  );
}

describe("messages", () => {
  it("English and Arabic define exactly the same keys", () => {
    expect(keys(ar).sort()).toEqual(keys(en).sort());
  });
  it("has no empty strings", () => {
    for (const m of [en, ar]) expect(leaves(m).every((s) => s.trim().length > 0)).toBe(true);
  });
  it("Arabic messages use Western digits only", () => {
    expect(leaves(ar).join(" ")).not.toMatch(/[٠-٩۰-۹]/);
  });
});

describe("locales", () => {
  it("maps direction per locale", () => {
    expect(dirOf("en")).toBe("ltr");
    expect(dirOf("ar")).toBe("rtl");
  });
  it("validates locale strings", () => {
    expect(locales.every(isLocale)).toBe(true);
    expect(isLocale("fr")).toBe(false);
  });
  it("formats numbers with Western digits by default, including Arabic", () => {
    expect(formatNumber(25, "ar")).toBe("25");
    expect(formatNumber(1234.5, "ar")).toMatch(/^1[,٬]?234[.٫]5$/);
    expect(formatNumber(1234.5, "ar")).not.toMatch(/[٠-٩]/);
  });
  it("can opt in to Arabic-Indic digits for display", () => {
    expect(formatNumber(25, "ar", {}, "arabic-indic")).toBe("٢٥");
  });
  it("formats dates with Western digits in Arabic", () => {
    expect(formatDate(new Date("2026-03-31T00:00:00Z"), "ar")).not.toMatch(/[٠-٩]/);
  });
});
