"use client";

import { useLocale, useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import type { Locale } from "@/i18n/locales";
import { auth } from "@/lib/api";
import { useSession } from "@/lib/session";

export function LocaleSwitcher() {
  const t = useTranslations("Locale");
  const pathname = usePathname();
  const current = useLocale() as Locale;
  const target: Locale = current === "ar" ? "en" : "ar";
  const session = useSession();

  return (
    <Link
      href={pathname}
      locale={target}
      className="lang-switch"
      lang={target}
      hrefLang={target}
      aria-label={t("switchLabel")}
      onClick={() => {
        // Persist the preference for signed-in users (best effort; navigation proceeds regardless).
        if (session.status === "authenticated") {
          auth.updateMe({ locale: target }).then(session.setUser).catch(() => undefined);
        }
      }}
    >
      {t("switchTo")}
    </Link>
  );
}
