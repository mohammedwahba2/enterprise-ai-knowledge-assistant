"use client";

import { useId, useState, type ReactNode } from "react";
import { useTranslations } from "next-intl";
import { describeError, type ErrorView } from "@/lib/errors";

export function FormError({ error }: { error: ErrorView | null }) {
  const t = useTranslations("Errors");
  if (!error) return null;
  return (
    <div className="form-error" role="alert">
      <p>{t(error.key, error.values)}</p>
      {error.reasons.length > 0 && (
        <ul>
          {error.reasons.map((r) => (
            <li key={r}>{t(`reasons.${r}`)}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

type FieldProps = {
  label: string;
  name: string;
  type?: "text" | "email" | "password";
  autoComplete: string;
  value: string;
  onChange: (v: string) => void;
  hint?: string;
  required?: boolean;
  autoFocus?: boolean;
  /** Latin-script values (emails, passwords) get dir="auto" so they align sensibly in RTL pages. */
  autoDir?: boolean;
};

export function Field({ label, name, type = "text", hint, onChange, autoDir, ...rest }: FieldProps) {
  const id = useId();
  const t = useTranslations("Auth");
  const [shown, setShown] = useState(false);
  const isPassword = type === "password";
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className="field-control">
        <input
          id={id}
          name={name}
          type={isPassword && shown ? "text" : type}
          dir={autoDir ? "auto" : undefined}
          spellCheck={false}
          autoCapitalize="none"
          aria-describedby={hint ? `${id}-hint` : undefined}
          onChange={(e) => onChange(e.target.value)}
          {...rest}
        />
        {isPassword && (
          <button
            type="button"
            className="field-toggle"
            aria-pressed={shown}
            onClick={() => setShown((s) => !s)}
          >
            {shown ? t("hidePassword") : t("showPassword")}
          </button>
        )}
      </div>
      {hint && (
        <p className="field-hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function useSubmit() {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorView | null>(null);
  async function run(action: () => Promise<void>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await action();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setBusy(false);
    }
  }
  return { busy, error, run, setError };
}

export function SubmitButton({ busy, children }: { busy: boolean; children: ReactNode }) {
  return (
    <button type="submit" className="btn-primary" disabled={busy} aria-busy={busy}>
      {children}
    </button>
  );
}
