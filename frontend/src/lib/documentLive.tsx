"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { documents, type DocumentEvent, type StatusSummary } from "./api";

type Listener = (event: DocumentEvent | null) => void;

type Live = {
  summary: StatusSummary | null;
  /** Called for every progress event, and with `null` when the connection could not be kept (poll instead). */
  subscribe: (listener: Listener) => () => void;
  /** Re-read the summary now (after an upload, delete or reprocess). */
  refresh: () => void;
};

const LiveContext = createContext<Live | null>(null);

const POLL_MS = 5000;

/**
 * One progress connection per workspace per tab. Prefers server-sent events (the API re-authorizes
 * each event for the caller); when the stream cannot be opened it tells subscribers to poll.
 */
export function DocumentLiveProvider({ orgId, children }: { orgId: string; children: ReactNode }) {
  const [summary, setSummary] = useState<StatusSummary | null>(null);
  const listeners = useRef(new Set<Listener>());

  const refresh = useCallback(() => {
    documents
      .summary(orgId)
      .then(setSummary)
      .catch(() => undefined);
  }, [orgId]);

  useEffect(() => {
    // Initial and per-workspace load of the badge count: an external system filling state.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setSummary(null);
    refresh();
    const emit = (event: DocumentEvent | null) => listeners.current.forEach((l) => l(event));

    let source: EventSource | null = null;
    let poll: ReturnType<typeof setInterval> | null = null;
    let closed = false;

    const startPolling = () => {
      if (poll || closed) return;
      poll = setInterval(() => {
        refresh();
        emit(null);
      }, POLL_MS);
    };

    if (typeof EventSource === "undefined") {
      startPolling();
    } else {
      source = new EventSource(documents.eventsUrl(orgId), { withCredentials: true });
      source.addEventListener("document", (message) => {
        try {
          emit(JSON.parse((message as MessageEvent<string>).data) as DocumentEvent);
        } catch {
          emit(null);
        }
        refresh();
      });
      // EventSource reconnects by itself; while it is down, poll so the UI never goes stale.
      source.onerror = () => startPolling();
      source.onopen = () => {
        if (poll) {
          clearInterval(poll);
          poll = null;
        }
        refresh();
        emit(null);
      };
    }

    return () => {
      closed = true;
      source?.close();
      if (poll) clearInterval(poll);
    };
  }, [orgId, refresh]);

  const subscribe = useCallback((listener: Listener) => {
    listeners.current.add(listener);
    return () => {
      listeners.current.delete(listener);
    };
  }, []);

  const value = useMemo(() => ({ summary, subscribe, refresh }), [summary, subscribe, refresh]);
  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}

export function useDocumentLive(): Live {
  const live = useContext(LiveContext);
  if (!live) throw new Error("useDocumentLive must be used inside DocumentLiveProvider");
  return live;
}
