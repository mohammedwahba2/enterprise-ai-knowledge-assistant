"use client";

import type { ReactNode } from "react";
import { useTranslations } from "next-intl";
import { Link, usePathname } from "@/i18n/navigation";
import { Icon, type IconName } from "./Icon";
import { LocaleSwitcher } from "./LocaleSwitcher";
import { useCurrentOrg } from "./OrgGate";
import { OrgSwitcher } from "./OrgSwitcher";
import { UserMenu } from "./UserMenu";

type Item = { key: "ask" | "library" | "attention" | "collections"; icon: IconName };

const ITEMS: Item[] = [
  { key: "ask", icon: "ask" },
  { key: "library", icon: "library" },
  { key: "attention", icon: "attention" },
  { key: "collections", icon: "collections" },
];

export function AppShell({ children }: { children: ReactNode }) {
  const t = useTranslations();
  const org = useCurrentOrg();
  const pathname = usePathname();
  const current = pathname.startsWith(`/${org.slug}/library`) ? "library" : "ask";

  // Ask and Library exist so far; other destinations are rendered disabled, not as dead links.
  const hrefs: Partial<Record<Item["key"], string>> = {
    ask: `/${org.slug}`,
    library: `/${org.slug}/library`,
  };
  const renderItem = (item: Item) =>
    hrefs[item.key] ? (
      <Link
        key={item.key}
        href={hrefs[item.key]!}
        className="nav-item"
        aria-current={current === item.key ? "page" : undefined}
      >
        <Icon name={item.icon} />
        <span className="label">{t(`Nav.${item.key}`)}</span>
      </Link>
    ) : (
      <span key={item.key} className="nav-item" aria-disabled="true" title={t("Nav.comingSoon")}>
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
          <OrgSwitcher current={org} />
          <nav aria-label={t("Nav.primary")}>{ITEMS.map(renderItem)}</nav>
          <div className="rail-foot">
            <UserMenu />
            <LocaleSwitcher />
          </div>
        </aside>
        <main className="main">
          <header className="topbar" dir="auto">
            {org.name}
          </header>
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
