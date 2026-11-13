"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { auth } from "@/lib/api";
import { safeNext } from "@/lib/redirect";
import { useSession } from "@/lib/session";
import { Field, FormError, SubmitButton, useSubmit } from "./AuthForm";

export function SignInForm({ next }: { next: string | null }) {
  const t = useTranslations("Auth");
  const locale = useLocale();
  const router = useRouter();
  const session = useSession();
  const { busy, error, run } = useSubmit();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    if (session.status === "authenticated") router.replace(safeNext(next));
  }, [session.status, next, router]);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      const user = await auth.signIn(email.trim(), password);
      session.setUser(user);
      // Honour the saved language preference.
      router.replace(safeNext(next), { locale: user.locale ?? locale });
    });
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{t("signIn.title")}</h1>
      <FormError error={error} />
      <Field label={t("email")} name="email" type="email" autoComplete="username" autoDir autoFocus required value={email} onChange={setEmail} />
      <Field label={t("password")} name="password" type="password" autoComplete="current-password" autoDir required value={password} onChange={setPassword} />
      <SubmitButton busy={busy}>{t("signIn.submit")}</SubmitButton>
      <p className="auth-links">
        <Link href="/forgot-password">{t("signIn.forgot")}</Link>
      </p>
      <p className="auth-links">
        {t("signIn.noAccount")} <Link href="/sign-up">{t("signIn.createAccount")}</Link>
      </p>
    </form>
  );
}
