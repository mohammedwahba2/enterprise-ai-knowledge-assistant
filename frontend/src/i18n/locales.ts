export const locales = ["en", "ar"] as const;
export type Locale = (typeof locales)[number];
export const defaultLocale: Locale = "en";

export function isLocale(value: string): value is Locale {
  return (locales as readonly string[]).includes(value);
}

export function dirOf(locale: Locale): "ltr" | "rtl" {
  return locale === "ar" ? "rtl" : "ltr";
}

/**
 * Numbers and dates use Western digits (0-9) by default, including in Arabic (approved decision D11).
 * Arabic-Indic display becomes a per-user preference in a later stage; this is the only place to change.
 */
export type DigitStyle = "western" | "arabic-indic";

export function formatNumber(
  value: number,
  locale: Locale,
  options: Intl.NumberFormatOptions = {},
  digitStyle: DigitStyle = "western",
): string {
  return new Intl.NumberFormat(locale, {
    ...options,
    numberingSystem: digitStyle === "western" ? "latn" : "arab",
  }).format(value);
}

export function formatDate(
  value: Date,
  locale: Locale,
  options: Intl.DateTimeFormatOptions = { dateStyle: "medium" },
  digitStyle: DigitStyle = "western",
): string {
  return new Intl.DateTimeFormat(locale, {
    ...options,
    numberingSystem: digitStyle === "western" ? "latn" : "arab",
  }).format(value);
}
