"use client";

import { useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { auth } from "@/lib/api";
import type { Locale } from "@/i18n/locales";
import { passwordLengthOk, PASSWORD_MIN } from "@/lib/passwordPolicy";
import { useSession } from "@/lib/session";
import { Field, FormError, SubmitButton, useSubmit } from "./AuthForm";

export function SignUpForm() {
  const t = useTranslations("Auth");
  const locale = useLocale() as Locale;
  const router = useRouter();
  const session = useSession();
  const { busy, error, run, setError } = useSubmit();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!passwordLengthOk(password)) {
      setError({ key: "WEAK_PASSWORD", reasons: [password.length < PASSWORD_MIN ? "TOO_SHORT" : "TOO_LONG"] });
      return;
    }
    void run(async () => {
      const user = await auth.signUp({ email: email.trim(), password, display_name: name.trim(), locale });
      session.setUser(user);
      router.replace("/");
    });
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{t("signUp.title")}</h1>
      <FormError error={error} />
      <Field label={t("signUp.name")} name="name" autoComplete="name" autoFocus required value={name} onChange={setName} />
      <Field label={t("email")} name="email" type="email" autoComplete="username" autoDir required value={email} onChange={setEmail} />
      <Field
        label={t("password")}
        name="password"
        type="password"
        autoComplete="new-password"
        autoDir
        required
        value={password}
        onChange={setPassword}
        hint={t("signUp.passwordHint", { min: String(PASSWORD_MIN) })}
      />
      <SubmitButton busy={busy}>{t("signUp.submit")}</SubmitButton>
      <p className="auth-links">
        {t("signUp.haveAccount")} <Link href="/sign-in">{t("signUp.signInLink")}</Link>
      </p>
    </form>
  );
}
