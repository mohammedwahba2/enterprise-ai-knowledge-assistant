import type { Metadata } from "next";
import type { ReactNode } from "react";
import { notFound } from "next/navigation";
import { NextIntlClientProvider, hasLocale } from "next-intl";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { dirOf, type Locale } from "@/i18n/locales";
import { routing } from "@/i18n/routing";
import { SessionProvider } from "@/lib/session";
import "@/styles/globals.css";

type Props = { children: ReactNode; params: Promise<{ locale: string }> };

export function generateStaticParams() {
  return routing.locales.map((locale) => ({ locale }));
}

export async function generateMetadata({ params }: Pick<Props, "params">): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "App" });
  return { title: t("name") };
}

export default async function LocaleLayout({ children, params }: Props) {
  const { locale } = await params;
  if (!hasLocale(routing.locales, locale)) notFound();
  setRequestLocale(locale);

  return (
    <html lang={locale} dir={dirOf(locale as Locale)}>
      <body>
        <NextIntlClientProvider>
          <SessionProvider>{children}</SessionProvider>
        </NextIntlClientProvider>
      </body>
    </html>
  );
}
