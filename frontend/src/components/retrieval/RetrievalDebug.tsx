"use client";

import { useState, type FormEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import { search, type DebugResponse } from "@/lib/api";
import { describeError, type ErrorView } from "@/lib/errors";
import { formatNumber, type Locale } from "@/i18n/locales";
import { useCurrentOrg } from "../OrgGate";
import { FormError } from "../auth/AuthForm";

/**
 * Administrator tool: shows how a query is answered by each retrieval leg and how they are fused.
 * The API refuses non-administrators (403); this page only chooses what to render.
 */
export function RetrievalDebug() {
  const t = useTranslations("Retrieval");
  const locale = useLocale() as Locale;
  const org = useCurrentOrg();
  const isAdmin = org.role === "owner" || org.role === "admin";
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ErrorView | null>(null);
  const [result, setResult] = useState<DebugResponse | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  if (!isAdmin) {
    return (
      <section className="lib">
        <h1>{t("title")}</h1>
        <p className="muted">{t("adminOnly")}</p>
      </section>
    );
  }

  async function run(e: FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await search.debug(org.id, query.trim(), 10));
      setOpen(null);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setBusy(false);
    }
  }

  const score = (value: number | null, digits = 3) =>
    value === null ? "—" : formatNumber(value, locale, { minimumFractionDigits: digits, maximumFractionDigits: digits });

  return (
    <section className="lib">
      <div className="lh">
        <h1>{t("title")}</h1>
      </div>
      <p className="muted">{t("intro")}</p>
      <form className="rd-form" onSubmit={run} role="search">
        <input
          className="fsearch"
          type="search"
          value={query}
          maxLength={1000}
          placeholder={t("placeholder")}
          aria-label={t("placeholder")}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" className="btnp" disabled={busy || !query.trim()}>
          {busy ? t("searching") : t("search")}
        </button>
      </form>
      <FormError error={error} />

      {result && (
        <>
          <p className="rd-meta" role="status">
            <span>{t("model", { model: result.embedding_model })}</span>
            <span>{t("collections", { count: result.accessible_collections })}</span>
            <span>{t("candidates", { vector: result.vector_candidates, fts: result.fts_candidates })}</span>
            <span>{t("timing", { ms: Math.round(result.timings_ms.total ?? 0) })}</span>
            {result.degraded && <strong className="rd-degraded">{t("degraded")}</strong>}
          </p>
          {result.hits.length === 0 ? (
            <div className="lib-empty">
              <h2>{t("noResults")}</h2>
            </div>
          ) : (
            <div className="tw">
              <table>
                <thead>
                  <tr>
                    <th className="n">#</th>
                    <th>{t("columns.chunk")}</th>
                    <th className="n">{t("columns.vector")}</th>
                    <th className="n">{t("columns.fts")}</th>
                    <th className="n">{t("columns.fused")}</th>
                  </tr>
                </thead>
                <tbody>
                  {result.hits.map((h, i) => (
                    <tr key={h.chunk_id}>
                      <td className="n">{i + 1}</td>
                      <td className="t">
                        <b><bdi>{h.document_title}</bdi></b>
                        <small>
                          <bdi>{h.collection_name}</bdi> · {t("pages", { from: h.page_start, to: h.page_end })} · {h.lang.toUpperCase()}
                          {h.heading_path ? <> · <bdi>{h.heading_path}</bdi></> : null}
                        </small>
                        <button type="button" className="linklike" onClick={() => setOpen(open === h.chunk_id ? null : h.chunk_id)}>
                          {open === h.chunk_id ? t("hideText") : t("showText")}
                        </button>
                        {open === h.chunk_id && <p className="rd-text" dir="auto">{h.content}</p>}
                      </td>
                      <td className="n">{h.vector_rank === null ? "—" : `#${h.vector_rank} · ${score(h.vector_score)}`}</td>
                      <td className="n">{h.fts_rank === null ? "—" : `#${h.fts_rank} · ${score(h.fts_score)}`}</td>
                      <td className="n">{score(h.score, 4)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}
