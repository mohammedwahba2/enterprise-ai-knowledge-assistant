"use client";

import { useEffect } from "react";
import { useRouter } from "@/i18n/navigation";
import { pickOrg, recallOrg, useOrgs } from "@/lib/orgs";
import { useSession } from "@/lib/session";

/** `/[locale]` has no content of its own: send people to a workspace, or to create one. */
export function RootRedirect() {
  const router = useRouter();
  const { status, orgs } = useOrgs();
  const { user } = useSession();

  useEffect(() => {
    if (status !== "ready" || !user) return;
    const target = pickOrg(orgs, recallOrg(user.id));
    router.replace(target ? `/${target.slug}` : "/create-workspace");
  }, [status, orgs, user, router]);

  return <div className="boot" role="status" />;
}
