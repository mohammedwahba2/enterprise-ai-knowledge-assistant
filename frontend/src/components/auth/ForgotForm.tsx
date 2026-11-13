"use client";

import { useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { auth } from "@/lib/api";
import type { Locale } from "@/i18n/locales";
import { Field, FormError, SubmitButton, useSubmit } from "./AuthForm";

export function ForgotForm() {
  const t = useTranslations("Auth");
  const locale = useLocale() as Locale;
  const { busy, error, run } = useSubmit();
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      await auth.forgot(email.trim(), locale);
      setSent(true);
    });
  }

  if (sent) {
    return (
      <div>
        <h1>{t("forgot.sentTitle")}</h1>
        <p className="auth-body" role="status">{t("forgot.sentBody", { minutes: "30" })}</p>
        <p className="auth-links"><Link href="/sign-in">{t("backToSignIn")}</Link></p>
      </div>
    );
  }
  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{t("forgot.title")}</h1>
      <p className="auth-body">{t("forgot.body")}</p>
      <FormError error={error} />
      <Field label={t("email")} name="email" type="email" autoComplete="username" autoDir autoFocus required value={email} onChange={setEmail} />
      <SubmitButton busy={busy}>{t("forgot.submit")}</SubmitButton>
      <p className="auth-links"><Link href="/sign-in">{t("backToSignIn")}</Link></p>
    </form>
  );
}
