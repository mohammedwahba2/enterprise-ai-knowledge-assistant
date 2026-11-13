import type { ReactNode } from "react";
import { getTranslations } from "next-intl/server";
import { Link } from "@/i18n/navigation";
import { Icon, type IconName } from "./Icon";
import { LocaleSwitcher } from "./LocaleSwitcher";
import { UserMenu } from "./UserMenu";

type Item = { key: "ask" | "library" | "attention" | "collections"; icon: IconName };

const ITEMS: Item[] = [
  { key: "ask", icon: "ask" },
  { key: "library", icon: "library" },
  { key: "attention", icon: "attention" },
  { key: "collections", icon: "collections" },
];

export async function AppShell({ children }: { children: ReactNode }) {
  const t = await getTranslations();

  // Only "Ask" exists in stage 1; other destinations are rendered disabled, not as dead links.
  const renderItem = (item: Item) =>
    item.key === "ask" ? (
      <Link key={item.key} href="/" className="nav-item" aria-current="page">
        <Icon name={item.icon} />
        <span className="label">{t(`Nav.${item.key}`)}</span>
      </Link>
    ) : (
      <span
        key={item.key}
        className="nav-item"
        aria-disabled="true"
        title={t("Nav.comingSoon")}
      >
        <Icon name={item.icon} />
        <span className="label">{t(`Nav.${item.key}`)}</span>
      </span>
    );

  return (
    <>
      <a className="skip-link" href="#content">
        {t("App.skipToContent")}
      </a>
      <div className="shell">
        <aside className="rail">
          <div className="org">
            <span className="org-mark" aria-hidden="true">
              KA
            </span>
            <span className="label">{t("App.name")}</span>
          </div>
          <nav aria-label={t("Nav.primary")}>{ITEMS.map(renderItem)}</nav>
          <div className="rail-foot">
            <UserMenu />
            <LocaleSwitcher />
          </div>
        </aside>
        <main className="main">
          <header className="topbar">{t("Nav.ask")}</header>
          <div className="content" id="content" tabIndex={-1}>
            {children}
          </div>
        </main>
        <nav className="tabbar" aria-label={t("Nav.primary")}>
          {ITEMS.slice(0, 3).map(renderItem)}
        </nav>
      </div>
    </>
  );
}
