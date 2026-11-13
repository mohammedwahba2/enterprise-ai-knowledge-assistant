"use client";

import { useEffect, useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { auth } from "@/lib/api";
import { takeTokenFromHash } from "@/lib/resetToken";
import { passwordLengthOk, PASSWORD_MIN } from "@/lib/passwordPolicy";
import { Field, FormError, SubmitButton, useSubmit } from "./AuthForm";

export function ResetForm() {
  const t = useTranslations("Auth");
  const { busy, error, run, setError } = useSubmit();
  const [token, setToken] = useState<string | null | undefined>(undefined);
  const [password, setPassword] = useState("");
  const [done, setDone] = useState(false);

  useEffect(() => {
    // Reads window.location once after hydration (external system), then scrubs it.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setToken(takeTokenFromHash());
  }, []);

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!token) return;
    if (!passwordLengthOk(password)) {
      setError({ key: "WEAK_PASSWORD", reasons: [password.length < PASSWORD_MIN ? "TOO_SHORT" : "TOO_LONG"] });
      return;
    }
    void run(async () => {
      await auth.reset(token, password);
      setDone(true);
    });
  }

  if (token === undefined) return null; // before the fragment has been read
  if (done) {
    return (
      <div>
        <h1>{t("reset.doneTitle")}</h1>
        <p className="auth-body" role="status">{t("reset.done")}</p>
        <p className="auth-links"><Link href="/sign-in">{t("signIn.title")}</Link></p>
      </div>
    );
  }
  if (token === null) {
    return (
      <div>
        <h1>{t("reset.title")}</h1>
        <p className="form-error" role="alert">{t("reset.missingToken")}</p>
        <p className="auth-links"><Link href="/forgot-password">{t("forgot.submit")}</Link></p>
      </div>
    );
  }
  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{t("reset.title")}</h1>
      <FormError error={error} />
      <Field
        label={t("reset.password")}
        name="password"
        type="password"
        autoComplete="new-password"
        autoDir
        autoFocus
        required
        value={password}
        onChange={setPassword}
        hint={t("signUp.passwordHint", { min: String(PASSWORD_MIN) })}
      />
      <SubmitButton busy={busy}>{t("reset.submit")}</SubmitButton>
    </form>
  );
}
