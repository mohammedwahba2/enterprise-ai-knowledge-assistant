"use client";

import { useCallback, useEffect, useRef, useState, type DragEvent } from "react";
import { useLocale, useTranslations } from "next-intl";
import {
  collections as collectionsApi,
  documents as documentsApi,
  type Collection,
  type DocumentItem,
  type UploadResult,
} from "@/lib/api";
import { describeError, type ErrorView } from "@/lib/errors";
import { ACCEPT_ATTR, formatBytes, preflight } from "@/lib/files";
import { formatDate, type Locale } from "@/i18n/locales";
import { useDocumentLive } from "@/lib/documentLive";
import { isProcessing, NEEDS_ATTENTION, toneOf } from "@/lib/documentStatus";
import { useCurrentOrg } from "../OrgGate";
import { FormError } from "../auth/AuthForm";
import { AttentionPanel } from "./AttentionPanel";

type Outcome = { filename: string; kind: "created" | "duplicate" | "rejected"; reason?: string };

export function LibraryPage() {
  const t = useTranslations("Library");
  const locale = useLocale() as Locale;
  const org = useCurrentOrg();
  const canWrite = org.role === "owner" || org.role === "admin" || org.role === "editor";
  const fileInput = useRef<HTMLInputElement>(null);

  const [collections, setCollections] = useState<Collection[]>([]);
  const [filter, setFilter] = useState<string>("");
  const [query, setQuery] = useState("");
  const [debounced, setDebounced] = useState("");
  const [items, setItems] = useState<DocumentItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ErrorView | null>(null);
  const [uploading, setUploading] = useState(false);
  const [target, setTarget] = useState<string>("");
  const [outcomes, setOutcomes] = useState<Outcome[]>([]);
  const [dragging, setDragging] = useState(false);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [attention, setAttention] = useState<DocumentItem[]>([]);
  const [reprocessing, setReprocessing] = useState<ReadonlySet<string>>(new Set());
  const live = useDocumentLive();

  const units = {
    b: t("units.b"),
    kb: t("units.kb"),
    mb: t("units.mb"),
    gb: t("units.gb"),
  };

  const load = useCallback(
    async (opts: { append?: boolean; cursor?: string | null } = {}) => {
      try {
        const page = await documentsApi.list(org.id, {
          collection_id: filter || undefined,
          q: debounced,
          cursor: opts.cursor ?? null,
        });
        setItems((prev) => (opts.append ? [...prev, ...page.items] : page.items));
        setCursor(page.next_cursor);
        setError(null);
      } catch (e) {
        setError(describeError(e));
      } finally {
        setLoading(false);
      }
    },
    [org.id, filter, debounced],
  );

  const loadAttention = useCallback(async () => {
    try {
      const pages = await Promise.all(
        NEEDS_ATTENTION.map((status) => documentsApi.list(org.id, { status, limit: 20 })),
      );
      const merged = pages.flatMap((p) => p.items).sort((a, b) => b.created_at.localeCompare(a.created_at));
      setAttention(merged);
    } catch {
      /* the panel is secondary; the table still shows every status */
    }
  }, [org.id]);

  // Keep the table and the attention panel current from worker progress events (or polling).
  const loadRef = useRef(load);
  const loadAttentionRef = useRef(loadAttention);
  useEffect(() => {
    loadRef.current = load;
    loadAttentionRef.current = loadAttention;
  }, [load, loadAttention]);
  const itemsRef = useRef(items);
  useEffect(() => {
    itemsRef.current = items;
  }, [items]);
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    const reload = () => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => {
        void loadRef.current();
        void loadAttentionRef.current();
      }, 250);
    };
    const off = live.subscribe((event) => {
      if (event === null) {
        // Polling mode: only refetch while something is still in flight.
        if (itemsRef.current.some((d) => isProcessing(d.status))) reload();
        return;
      }
      const known = itemsRef.current.some((d) => d.id === event.document_id);
      if (known) {
        setItems((prev) =>
          prev.map((d) => (d.id === event.document_id ? { ...d, status: event.status, error_code: event.error_code } : d)),
        );
      }
      // Page counts, language and unreadable ranges arrive with the final state: refetch then.
      if (!known || !isProcessing(event.status)) reload();
    });
    return () => {
      off();
      if (timer) clearTimeout(timer);
    };
  }, [live]);

  useEffect(() => {
    // Org-wide attention list: an external system (the API) filling state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadAttention();
  }, [loadAttention]);

  useEffect(() => {
    const id = setTimeout(() => setDebounced(query), 300);
    return () => clearTimeout(id);
  }, [query]);

  useEffect(() => {
    let cancelled = false;
    collectionsApi
      .list(org.id)
      .then((cols) => {
        if (cancelled) return;
        setCollections(cols);
        setTarget((cur) => cur || cols.find((c) => c.can_upload)?.id || "");
      })
      .catch((e) => !cancelled && setError(describeError(e)));
    return () => {
      cancelled = true;
    };
  }, [org.id]);

  useEffect(() => {
    // Reload whenever the filter or search changes: an external system (the API) filling state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setLoading(true);
    void load();
  }, [load]);

  async function upload(files: File[]) {
    if (!files.length || !canWrite) return;
    const collectionId = (filter && collections.find((c) => c.id === filter)?.id) || target;
    if (!collectionId) return;
    const next: Outcome[] = [];
    const sendable: File[] = [];
    for (const file of files) {
      const bad = preflight(file);
      if (bad) next.push({ filename: file.name, kind: "rejected", reason: bad });
      else sendable.push(file);
    }
    setUploading(true);
    setError(null);
    try {
      if (sendable.length) {
        const results: UploadResult[] = await documentsApi.upload(org.id, collectionId, sendable);
        for (const r of results) {
          next.push({
            filename: r.filename,
            kind: r.outcome,
            reason: r.error_code ?? undefined,
          });
        }
      }
    } catch (e) {
      setError(describeError(e));
    } finally {
      setUploading(false);
      setOutcomes(next);
      setLoading(true);
      void load();
      void loadAttention();
      live.refresh();
      void collectionsApi.list(org.id).then(setCollections);
    }
  }

  async function remove(doc: DocumentItem) {
    setConfirming(null);
    try {
      await documentsApi.remove(org.id, doc.id);
      setItems((prev) => prev.filter((d) => d.id !== doc.id));
      setAttention((prev) => prev.filter((d) => d.id !== doc.id));
      live.refresh();
      void collectionsApi.list(org.id).then(setCollections);
    } catch (e) {
      setError(describeError(e));
    }
  }

  async function reprocess(doc: DocumentItem) {
    setReprocessing((prev) => new Set(prev).add(doc.id));
    try {
      await documentsApi.reprocess(org.id, doc.id);
      setItems((prev) => prev.map((d) => (d.id === doc.id ? { ...d, status: "uploaded", error_code: null } : d)));
      setAttention((prev) => prev.filter((d) => d.id !== doc.id));
      live.refresh();
    } catch (e) {
      setError(describeError(e));
    } finally {
      setReprocessing((prev) => {
        const next = new Set(prev);
        next.delete(doc.id);
        return next;
      });
    }
  }

  const onDrop = (e: DragEvent) => {
    e.preventDefault();
    setDragging(false);
    void upload([...e.dataTransfer.files]);
  };

  const filtered = Boolean(filter || debounced);
  const dropName = collections.find((c) => c.id === (filter || target))?.name ?? "";

  return (
    <section
      className="lib"
      onDragOver={(e) => {
        if (canWrite && e.dataTransfer.types.includes("Files")) {
          e.preventDefault();
          setDragging(true);
        }
      }}
      onDragLeave={(e) => {
        if (e.currentTarget === e.target) setDragging(false);
      }}
      onDrop={onDrop}
    >
      {dragging && <div className="drop-overlay" aria-hidden="true">{t("dropHere", { collection: dropName })}</div>}
      <div className="lh">
        <h1>{t("title")}</h1>
        {canWrite && (
          <>
            {collections.filter((c) => c.can_upload).length > 1 && !filter && (
              <label className="upload-target">
                <span>{t("uploadTo")}</span>
                <select value={target} onChange={(e) => setTarget(e.target.value)}>
                  {collections.map((c) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
            )}
            <input
              ref={fileInput}
              type="file"
              multiple
              hidden
              accept={ACCEPT_ATTR}
              onChange={(e) => {
                void upload([...(e.target.files ?? [])]);
                e.target.value = "";
              }}
            />
            <button type="button" className="btnp" disabled={uploading || !target} onClick={() => fileInput.current?.click()}>
              {uploading ? t("uploading") : t("upload")}
            </button>
          </>
        )}
      </div>

      <FormError error={error} />

      {outcomes.length > 0 && (
        <div className="outcomes" role="status">
          <ul>
            {outcomes.map((o, i) => (
              <li key={`${o.filename}-${i}`} data-kind={o.kind}>
                <span className="of-name"><bdi>{o.filename}</bdi></span>
                <span className="of-state">
                  {t(`outcome.${o.kind}`)}
                  {o.reason ? ` — ${t(`reject.${o.reason}`)}` : ""}
                </span>
              </li>
            ))}
          </ul>
          <button type="button" className="linklike" onClick={() => setOutcomes([])}>{t("dismiss")}</button>
        </div>
      )}

      <AttentionPanel
        orgId={org.id}
        items={attention}
        canWrite={canWrite}
        busy={reprocessing}
        onReprocess={(d) => void reprocess(d)}
        onDelete={(d) => void remove(d)}
      />

      <div className="filters">
        <button type="button" className={`f${filter === "" ? " on" : ""}`} onClick={() => setFilter("")}>
          {t("allCollections")}
        </button>
        {collections.map((c) => (
          <button key={c.id} type="button" className={`f${filter === c.id ? " on" : ""}`} onClick={() => setFilter(c.id)}>
            <bdi>{c.name}</bdi>
            {c.visibility === "restricted" && <LockIcon label={t("restricted")} />}
            <b>{c.document_count}</b>
          </button>
        ))}
        <input
          className="fsearch"
          type="search"
          value={query}
          placeholder={t("search")}
          aria-label={t("search")}
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      {loading && items.length === 0 ? (
        <div className="boot" role="status" />
      ) : items.length === 0 ? (
        <div className="lib-empty">
          <h2>{filtered ? t("noMatches") : t("emptyTitle")}</h2>
          {!filtered && <p>{canWrite ? t("emptyEditor") : t("emptyViewer")}</p>}
        </div>
      ) : (
        <div className="tw">
          <table>
            <thead>
              <tr>
                <th>{t("columns.document")}</th>
                <th className="hm">{t("columns.collection")}</th>
                <th className="hm">{t("columns.language")}</th>
                <th className="n hm">{t("columns.pages")}</th>
                <th className="n hm">{t("columns.size")}</th>
                <th>{t("columns.status")}</th>
                <th className="n hm">{t("columns.uploaded")}</th>
                <th aria-hidden="true" />
              </tr>
            </thead>
            <tbody>
              {items.map((d) => {
                const col = collections.find((c) => c.id === d.collection_id);
                return (
                  <tr key={d.id} className={NEEDS_ATTENTION.some((s) => s === d.status) ? "attn-row" : undefined}>
                    <td className="t">
                      <b><bdi>{d.title}</bdi></b>
                      <small><bdi>{d.original_filename}</bdi></small>
                    </td>
                    <td className="hm">
                      <bdi>{d.collection_name}</bdi>
                      {col?.visibility === "restricted" && <LockIcon label={t("restricted")} />}
                    </td>
                    <td className="hm">
                      {d.language === "ar" || d.language === "en" ? (
                        <span className="lg">{t(`language.${d.language}`)}</span>
                      ) : d.language === "mixed" ? (
                        <span className="lg">{t("language.mixed")}</span>
                      ) : null}
                    </td>
                    <td className="n hm">{d.page_count ?? ""}</td>
                    <td className="n hm">{formatBytes(d.size_bytes, locale, units)}</td>
                    <td>
                      <span className={`st ${toneOf(d.status)}`}>{t(`status.${d.status}`)}</span>
                    </td>
                    <td className="n hm">{formatDate(new Date(d.created_at), locale)}</td>
                    <td className="actions">
                      {confirming === d.id ? (
                        <span className="confirm" role="alert">
                          <span className="confirm-q">{t("confirmDelete", { name: d.title })}</span>
                          <button type="button" className="danger" onClick={() => void remove(d)}>{t("confirm")}</button>
                          <button type="button" className="linklike" onClick={() => setConfirming(null)}>{t("cancel")}</button>
                        </span>
                      ) : (
                        <>
                          <a className="act" href={documentsApi.fileUrl(org.id, d.id, true)}>{t("download")}</a>
                          {canWrite && (
                            <button type="button" className="act danger-link" onClick={() => setConfirming(d.id)}>
                              {t("delete")}
                            </button>
                          )}
                        </>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
      {cursor && (
        <p className="load-more">
          <button type="button" className="f" onClick={() => void load({ append: true, cursor })}>{t("loadMore")}</button>
        </p>
      )}
    </section>
  );
}

function LockIcon({ label }: { label: string }) {
  return (
    <svg className="icon lock" viewBox="0 0 12 12" role="img" aria-label={label}>
      <title>{label}</title>
      <rect x="2.2" y="5.4" width="7.6" height="5" rx="1" />
      <path d="M4 5.4V4a2 2 0 0 1 4 0v1.4" />
    </svg>
  );
}
