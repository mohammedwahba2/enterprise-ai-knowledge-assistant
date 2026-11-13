"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslations } from "next-intl";
import { Link } from "@/i18n/navigation";
import { useOrgs } from "@/lib/orgs";
import type { Org } from "@/lib/api";

function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? [words[0], words[1]] : [...(words[0] ?? "?")].slice(0, 2);
  return letters.map((w) => [...(w ?? "")][0] ?? "").join("").toUpperCase();
}

export function OrgSwitcher({ current }: { current: Org }) {
  const t = useTranslations("Org");
  const { orgs } = useOrgs();
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (root.current && !root.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="org-switcher" ref={root}>
      <button
        type="button"
        className="org"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`${t("current")}: ${current.name}. ${t("switcherLabel")}`}
        onClick={() => setOpen((o) => !o)}
      >
        <span className="org-mark" aria-hidden="true">{initials(current.name)}</span>
        <span className="label org-name" dir="auto">{current.name}</span>
        <span className="label org-caret" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <ul className="org-menu" role="menu" aria-label={t("switcherLabel")}>
          {orgs.map((o) => (
            <li key={o.id} role="none">
              <Link
                role="menuitem"
                href={`/${o.slug}`}
                aria-current={o.id === current.id ? "true" : undefined}
                onClick={() => setOpen(false)}
              >
                <span className="org-mark" aria-hidden="true">{initials(o.name)}</span>
                <span dir="auto">{o.name}</span>
              </Link>
            </li>
          ))}
          <li role="none" className="org-menu-sep">
            <Link role="menuitem" href="/create-workspace" onClick={() => setOpen(false)}>
              {t("create")}
            </Link>
          </li>
        </ul>
      )}
    </div>
  );
}
