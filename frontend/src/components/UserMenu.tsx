"use client";

import { useTranslations } from "next-intl";
import { useRouter } from "@/i18n/navigation";
import { useSession } from "@/lib/session";

export function UserMenu() {
  const t = useTranslations("Auth");
  const router = useRouter();
  const { user, signOut } = useSession();
  if (!user) return null;
  return (
    <div className="user-menu">
      <span className="avatar" aria-hidden="true">{[...user.display_name][0]?.toUpperCase()}</span>
      <span className="label user-name" dir="auto" title={user.email}>{user.display_name}</span>
      <button
        type="button"
        className="signout"
        onClick={async () => {
          await signOut();
          router.replace("/sign-in");
        }}
      >
        {t("signOut")}
      </button>
    </div>
  );
}
