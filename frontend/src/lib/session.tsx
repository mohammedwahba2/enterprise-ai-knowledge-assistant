"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { auth, type User } from "./api";

type State =
  | { status: "loading"; user: null }
  | { status: "anonymous"; user: null }
  | { status: "authenticated"; user: User };

type Ctx = State & {
  setUser: (user: User) => void;
  signOut: () => Promise<void>;
};

const SessionContext = createContext<Ctx | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<State>({ status: "loading", user: null });

  useEffect(() => {
    let cancelled = false;
    auth
      .me()
      .then((user) => !cancelled && setState({ status: "authenticated", user }))
      .catch(() => {
        // Unauthenticated and unreachable both route to sign-in; the API enforces access anyway.
        if (!cancelled) setState({ status: "anonymous", user: null });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const setUser = useCallback((user: User) => setState({ status: "authenticated", user }), []);
  const signOut = useCallback(async () => {
    try {
      await auth.signOut();
    } finally {
      setState({ status: "anonymous", user: null });
    }
  }, []);

  const value = useMemo<Ctx>(() => ({ ...state, setUser, signOut }), [state, setUser, signOut]);
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Ctx {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used inside <SessionProvider>");
  return ctx;
}
