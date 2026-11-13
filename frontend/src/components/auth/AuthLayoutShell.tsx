import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";
import { LocaleSwitcher } from "@/components/LocaleSwitcher";

export async function AuthLayoutShell({ children }: { children: ReactNode }) {
  const t = await getTranslations("App");
  return (
    <div className="auth-page">
      <header className="auth-top">
        <span className="org">
          <span className="org-mark" aria-hidden="true">
            KA
          </span>
          <span>{t("name")}</span>
        </span>
        <LocaleSwitcher />
      </header>
      <main className="auth-main" id="content">
        {children}
      </main>
    </div>
  );
}
