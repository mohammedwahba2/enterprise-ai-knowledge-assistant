/**
 * Browser API client for the same-origin FastAPI backend.
 *
 * - Cookies carry the session (HttpOnly; JS never sees tokens).
 * - Unsafe methods send the double-submit CSRF token from the readable `ka_csrf` cookie.
 * - A 401 UNAUTHENTICATED triggers exactly one refresh (single-flight across calls and tabs),
 *   then one retry.
 */

export type Problem = {
  code?: string;
  title?: string;
  status?: number;
  reasons?: string[];
  errors?: { loc: string[]; msg: string; type: string }[];
  retry_after?: number;
};

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    public readonly problem: Problem = {},
    public readonly retryAfter?: number,
  ) {
    super(code);
    this.name = "ApiError";
  }
}

export type User = {
  id: string;
  email: string;
  display_name: string;
  locale: "en" | "ar";
  digit_style: "western" | "arabic-indic";
};

const BASE = "/api/v1";
const UNSAFE = new Set(["POST", "PUT", "PATCH", "DELETE"]);

export function readCookie(name: string): string {
  if (typeof document === "undefined") return "";
  const hit = document.cookie.split("; ").find((c) => c.startsWith(`${name}=`));
  return hit ? decodeURIComponent(hit.slice(name.length + 1)) : "";
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  if (init.body !== undefined && !headers.has("content-type")) {
    headers.set("content-type", "application/json");
  }
  if (UNSAFE.has(method)) {
    const csrf = readCookie("ka_csrf");
    if (csrf) headers.set("x-csrf-token", csrf);
  }
  try {
    return await fetch(`${BASE}${path}`, { ...init, method, headers, credentials: "same-origin" });
  } catch {
    throw new ApiError(0, "NETWORK");
  }
}

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) {
    return (res.status === 204 ? undefined : await res.json()) as T;
  }
  let problem: Problem = {};
  try {
    problem = (await res.json()) as Problem;
  } catch {
    /* non-JSON error body */
  }
  const retry = Number(res.headers.get("retry-after"));
  throw new ApiError(res.status, problem.code ?? "UNKNOWN", problem, retry > 0 ? retry : undefined);
}

let inFlightRefresh: Promise<boolean> | null = null;

async function doRefresh(): Promise<boolean> {
  try {
    await parse(await send("/auth/refresh", { method: "POST" }));
    return true;
  } catch (e) {
    // Another tab rotated the token a moment ago: our cookies are already fresh.
    return e instanceof ApiError && e.code === "REFRESH_RACE";
  }
}

export function refreshSession(): Promise<boolean> {
  if (inFlightRefresh) return inFlightRefresh;
  const run = async () => {
    const locks = typeof navigator !== "undefined" ? navigator.locks : undefined;
    if (!locks) return doRefresh();
    // Cross-tab single flight: whoever waits on the lock first checks whether a sibling tab
    // already refreshed, instead of rotating the token again.
    return locks.request("ka-refresh", async () => {
      try {
        await parse(await send("/auth/me"));
        return true;
      } catch {
        return doRefresh();
      }
    });
  };
  inFlightRefresh = run().finally(() => {
    inFlightRefresh = null;
  });
  return inFlightRefresh;
}

export async function request<T>(
  path: string,
  init: RequestInit = {},
  opts: { retryOn401?: boolean } = {},
): Promise<T> {
  const retryOn401 = opts.retryOn401 ?? true;
  try {
    return await parse<T>(await send(path, init));
  } catch (e) {
    if (retryOn401 && e instanceof ApiError && e.status === 401 && e.code === "UNAUTHENTICATED") {
      // No session hint cookie means there is nothing to refresh (anonymous visitor).
      if (readCookie("ka_session") && (await refreshSession())) return parse<T>(await send(path, init));
    }
    throw e;
  }
}

const json = (body: unknown): RequestInit => ({ method: "POST", body: JSON.stringify(body) });

export const auth = {
  me: () => request<User>("/auth/me"),
  signIn: (email: string, password: string) =>
    request<User>("/auth/sign-in", json({ email, password }), { retryOn401: false }),
  signUp: (input: { email: string; password: string; display_name: string; locale: "en" | "ar" }) =>
    request<User>("/auth/sign-up", json(input), { retryOn401: false }),
  signOut: () => request<void>("/auth/sign-out", { method: "POST" }, { retryOn401: false }),
  forgot: (email: string, locale: "en" | "ar") =>
    request<{ status: string }>("/auth/password/forgot", json({ email, locale }), { retryOn401: false }),
  reset: (token: string, password: string) =>
    request<void>("/auth/password/reset", json({ token, password }), { retryOn401: false }),
  updateMe: (patch: Partial<Pick<User, "locale" | "digit_style" | "display_name">>) =>
    request<User>("/auth/me", { method: "PATCH", body: JSON.stringify(patch) }),
};
