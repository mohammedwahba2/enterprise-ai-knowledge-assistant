"use client";

import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { Link, useRouter } from "@/i18n/navigation";
import { orgs as orgsApi } from "@/lib/api";
import { useOrgs } from "@/lib/orgs";
import { Field, FormError, SubmitButton, useSubmit } from "./auth/AuthForm";

export function CreateWorkspaceForm() {
  const t = useTranslations("Workspace");
  const router = useRouter();
  const { orgs, add } = useOrgs();
  const { busy, error, run } = useSubmit();
  const [name, setName] = useState("");

  function onSubmit(e: FormEvent) {
    e.preventDefault();
    void run(async () => {
      const org = await orgsApi.create(name.trim());
      add(org);
      router.replace(`/${org.slug}`);
    });
  }

  return (
    <form onSubmit={onSubmit} noValidate>
      <h1>{t("title")}</h1>
      <p className="auth-body">{t("body")}</p>
      <FormError error={error} />
      <Field label={t("name")} name="name" autoComplete="organization" autoFocus required value={name} onChange={setName} />
      <SubmitButton busy={busy}>{t("submit")}</SubmitButton>
      {orgs.length > 0 && (
        <p className="auth-links">
          <Link href="/">{t("cancel")}</Link>
        </p>
      )}
    </form>
  );
}
