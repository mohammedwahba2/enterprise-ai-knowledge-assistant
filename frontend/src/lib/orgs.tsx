"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { orgs as orgsApi, type Org } from "./api";

type State = { status: "loading" | "ready" | "error"; orgs: Org[] };
type Ctx = State & { add: (org: Org) => void; refresh: () => Promise<void> };

const OrgsContext = createContext<Ctx | null>(null);
// Keyed by user id: the browser is shared, the preference must not follow a different account.
const lastKey = (userId: string) => `ka_last_org:${userId}`;

/** Which workspace to open first: the last one used (if still accessible), else the first. */
export function pickOrg(orgs: Org[], lastSlug: string | null): Org | null {
  return orgs.find((o) => o.slug === lastSlug) ?? orgs[0] ?? null;
}

export function rememberOrg(userId: string, slug: string): void {
  try {
    window.localStorage.setItem(lastKey(userId), slug);
  } catch {
    /* storage unavailable (private mode): the preference is a convenience only */
  }
}

export function recallOrg(userId: string): string | null {
  try {
    return window.localStorage.getItem(lastKey(userId));
  } catch {
    return null;
  }
}

export function OrgsProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading", orgs: [] });

  const refresh = useCallback(async () => {
    try {
      setState({ status: "ready", orgs: await orgsApi.list() });
    } catch {
      setState((s) => ({ ...s, status: "error" }));
    }
  }, []);

  useEffect(() => {
    // Initial load: an external system (the API) populating state once on mount.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void refresh();
  }, [refresh]);

  const add = useCallback((org: Org) => {
    setState((s) => ({ status: "ready", orgs: [...s.orgs.filter((o) => o.id !== org.id), org] }));
  }, []);

  const value = useMemo<Ctx>(() => ({ ...state, add, refresh }), [state, add, refresh]);
  return <OrgsContext.Provider value={value}>{children}</OrgsContext.Provider>;
}

export function useOrgs(): Ctx {
  const ctx = useContext(OrgsContext);
  if (!ctx) throw new Error("useOrgs must be used inside <OrgsProvider>");
  return ctx;
}
