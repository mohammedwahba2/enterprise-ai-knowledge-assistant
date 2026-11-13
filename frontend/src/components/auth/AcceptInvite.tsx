"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { orgs as orgsApi } from "@/lib/api";
import { describeError, type ErrorView } from "@/lib/errors";
import { clearInviteToken, takeInviteToken } from "@/lib/inviteToken";
import { rememberOrg } from "@/lib/orgs";
import { useSession } from "@/lib/session";
import { FormError } from "./AuthForm";

export function AcceptInvite() {
  const t = useTranslations("Invite");
  const router = useRouter();
  const { status, user } = useSession();
  const started = useRef(false);
  const [error, setError] = useState<ErrorView | null>(null);
  const [missing, setMissing] = useState(false);

  useEffect(() => {
    if (status === "loading" || started.current) return;
    const token = takeInviteToken();
    if (!token) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setMissing(true);
      return;
    }
    if (status === "anonymous") {
      router.replace("/sign-in?next=%2Faccept-invite"); // the token waits in sessionStorage
      return;
    }
    started.current = true;
    orgsApi
      .acceptInvitation(token)
      .then((org) => {
        clearInviteToken();
        if (user) rememberOrg(user.id, org.slug);
        router.replace(`/${org.slug}`);
      })
      .catch((e) => {
        clearInviteToken();
        setError(describeError(e));
      });
  }, [status, user, router]);

  return (
    <div>
      <h1>{t("title")}</h1>
      {missing ? (
        <p className="form-error" role="alert">{t("missing")}</p>
      ) : error ? (
        <>
          <FormError error={error} />
          <p className="auth-links"><Link href="/">{t("continue")}</Link></p>
        </>
      ) : (
        <p className="auth-body" role="status">{t("accepting")}</p>
      )}
    </div>
  );
}
