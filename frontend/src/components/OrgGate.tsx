"use client";

import { createContext, useContext, useEffect, type ReactNode } from "react";
import { useParams } from "next/navigation";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { rememberOrg, useOrgs } from "@/lib/orgs";
import { useSession } from "@/lib/session";
import type { Org } from "@/lib/api";

const CurrentOrg = createContext<Org | null>(null);

export function useCurrentOrg(): Org {
  const org = useContext(CurrentOrg);
  if (!org) throw new Error("useCurrentOrg must be used inside <OrgGate>");
  return org;
}

/**
 * Resolves the `[org]` URL segment against the caller's own workspaces. An unknown slug and a
 * workspace you don't belong to look identical ("not found"): neither is revealed.
 * The API enforces membership on every request regardless of what this component renders.
 */
export function OrgGate({ children }: { children: ReactNode }) {
  const t = useTranslations("Org");
  const params = useParams<{ org: string }>();
  const { status, orgs } = useOrgs();
  const { user } = useSession();
  const org = orgs.find((o) => o.slug === params.org) ?? null;

  useEffect(() => {
    if (org && user) rememberOrg(user.id, org.slug);
  }, [org, user]);

  if (status === "loading") return <div className="boot" role="status" />;
  if (!org) {
    return (
      <main className="auth-main" id="content">
        <h1>{t("notFoundTitle")}</h1>
        <p className="auth-body">{t("notFoundBody")}</p>
        <p className="auth-links">
          <Link href="/">{t("backHome")}</Link>
        </p>
      </main>
    );
  }
  return <CurrentOrg.Provider value={org}>{children}</CurrentOrg.Provider>;
}
