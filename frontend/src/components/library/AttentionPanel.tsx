"use client";

import { useEffect, useMemo, useState } from "react";
import { useTranslations } from "next-intl";
import { documents as documentsApi, type DocumentItem, type PageInfo } from "@/lib/api";
import { formatRanges, isReasonCode, unreadableRanges } from "@/lib/documentStatus";

type Props = {
  orgId: string;
  items: DocumentItem[];
  canWrite: boolean;
  busy: ReadonlySet<string>;
  onReprocess: (doc: DocumentItem) => void;
  onDelete: (doc: DocumentItem) => void;
};

/** Documents the assistant cannot fully use, with the reason and what the viewer can do about it. */
export function AttentionPanel({ orgId, items, canWrite, busy, onReprocess, onDelete }: Props) {
  const t = useTranslations("Library");
  const [confirming, setConfirming] = useState<string | null>(null);
  if (items.length === 0) return null;
  return (
    <div className="attn" id="attention" tabIndex={-1} role="region" aria-label={t("attention.title", { count: items.length })}>
      <h3>
        <span className="ss-dot" aria-hidden="true" />
        <span>{t("attention.title", { count: items.length })}</span>
      </h3>
      {items.map((d) => (
        <div className="it" key={d.id}>
          <b><bdi>{d.original_filename}</bdi></b>
          <span className="d">
            <Reason orgId={orgId} doc={d} />
          </span>
          <span className="it-actions">
            {canWrite && (
              <button type="button" className="act" disabled={busy.has(d.id)} onClick={() => onReprocess(d)}>
                {busy.has(d.id) ? t("attention.reprocessing") : t("attention.reprocess")}
              </button>
            )}
            <a className="act" href={documentsApi.fileUrl(orgId, d.id, true)}>{t("download")}</a>
            {canWrite &&
              (confirming === d.id ? (
                <span className="confirm" role="alert">
                  <span className="confirm-q">{t("confirmDelete", { name: d.title })}</span>
                  <button type="button" className="danger" onClick={() => onDelete(d)}>{t("confirm")}</button>
                  <button type="button" className="linklike" onClick={() => setConfirming(null)}>{t("cancel")}</button>
                </span>
              ) : (
                <button type="button" className="act danger-link" onClick={() => setConfirming(d.id)}>{t("delete")}</button>
              ))}
          </span>
        </div>
      ))}
    </div>
  );
}

function Reason({ orgId, doc }: { orgId: string; doc: DocumentItem }) {
  const t = useTranslations("Library");
  const [pages, setPages] = useState<PageInfo[] | null>(null);
  const partial = doc.status === "ready_partial";

  useEffect(() => {
    if (!partial) return;
    let cancelled = false;
    documentsApi
      .pages(orgId, doc.id)
      .then((p) => !cancelled && setPages(p))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, [orgId, doc.id, partial, doc.page_count]);

  const ranges = useMemo(() => (pages ? formatRanges(unreadableRanges(pages)) : ""), [pages]);

  if (partial) {
    const total = doc.page_count ?? pages?.length ?? 0;
    const readable = doc.page_summary?.text ?? (pages ? pages.filter((p) => p.extraction_state === "text").length : 0);
    return <>{ranges ? t("reason.partialPages", { ranges, readable, total }) : t("reason.PARTIAL_TEXT")}</>;
  }
  if (doc.status === "unsupported_scanned") {
    return <>{t("reason.scanned", { pages: doc.page_count ?? 0 })}</>;
  }
  if (isReasonCode(doc.error_code)) return <>{t(`reason.${doc.error_code}`)}</>;
  return <>{t(`reason.fallback.${doc.status}`)}</>;
}
