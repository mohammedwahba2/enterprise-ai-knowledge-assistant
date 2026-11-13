"use client";

import { useEffect, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { usePathname, useRouter } from "@/i18n/navigation";
import { useSession } from "@/lib/session";

/** Client-side gate. Real enforcement is on the API; this only decides what to render. */
export function RequireSession({ children }: { children: ReactNode }) {
  const { status } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const t = useTranslations("Auth");

  useEffect(() => {
    if (status === "anonymous") {
      const next = pathname && pathname !== "/" ? `?next=${encodeURIComponent(pathname)}` : "";
      router.replace(`/sign-in${next}`);
    }
  }, [status, pathname, router]);

  if (status !== "authenticated") {
    return (
      <div className="boot" role="status" aria-live="polite">
        {t("loading")}
      </div>
    );
  }
  return <>{children}</>;
}
