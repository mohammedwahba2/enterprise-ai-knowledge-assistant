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
  // FormData must keep the browser-generated multipart boundary: never force a content type on it.
  if (typeof init.body === "string" && !headers.has("content-type")) {
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

const sleep = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

/**
 * REFRESH_RACE means a sibling request just rotated the token and its Set-Cookie may still be
 * in flight to this browser. The shared cookie jar converges on the single new token; poll the
 * session briefly instead of assuming it already has.
 */
async function waitForSiblingRotation(): Promise<boolean> {
  for (let attempt = 1; attempt <= 4; attempt++) {
    await sleep(150 * attempt);
    try {
      await parse(await send("/auth/me"));
      return true;
    } catch (e) {
      if (!(e instanceof ApiError && e.status === 401)) return false;
    }
  }
  return false;
}

async function doRefresh(): Promise<boolean> {
  try {
    await parse(await send("/auth/refresh", { method: "POST" }));
    return true;
  } catch (e) {
    if (e instanceof ApiError && e.code === "REFRESH_RACE") return waitForSiblingRotation();
    return false;
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

export type Org = { id: string; name: string; slug: string; role: "owner" | "admin" | "editor" | "member" | "viewer" };

export const orgs = {
  list: () => request<Org[]>("/orgs"),
  create: (name: string) => request<Org>("/orgs", json({ name })),
  acceptInvitation: (token: string) => request<Org>("/invitations/accept", json({ token })),
};

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

export type Collection = {
  id: string;
  name: string;
  description: string;
  visibility: "org" | "restricted";
  document_count: number;
  member_count: number | null;
  can_upload: boolean;
};

export type DocumentItem = {
  id: string;
  collection_id: string;
  collection_name: string;
  title: string;
  original_filename: string;
  mime_type: string;
  size_bytes: number;
  status: string;
  error_code: string | null;
  page_count: number | null;
  language: string | null;
  /** Count of pages per extraction state, e.g. `{ text: 48, image_only: 12 }`. */
  page_summary: Record<string, number> | null;
  uploaded_by_name: string | null;
  created_at: string;
};

export type DocumentPage = { items: DocumentItem[]; next_cursor: string | null };

export type PageInfo = {
  page_number: number;
  extraction_state: "text" | "image_only" | "garbled";
  char_count: number;
};

export type StatusSummary = { total: number; by_status: Record<string, number>; needs_attention: number };

/** One progress event pushed by the worker (relayed through the SSE endpoint). */
export type DocumentEvent = { document_id: string; status: string; error_code: string | null };

export type UploadResult = {
  filename: string;
  outcome: "created" | "duplicate" | "rejected";
  document: DocumentItem | null;
  error_code: string | null;
};

export const collections = {
  list: (orgId: string) => request<Collection[]>(`/orgs/${orgId}/collections`),
};

export const documents = {
  list: (
    orgId: string,
    p: { collection_id?: string; q?: string; status?: string; cursor?: string | null; limit?: number } = {},
  ) => {
    const qs = new URLSearchParams();
    if (p.collection_id) qs.set("collection_id", p.collection_id);
    if (p.status) qs.set("status", p.status);
    if (p.q?.trim()) qs.set("q", p.q.trim());
    if (p.cursor) qs.set("cursor", p.cursor);
    qs.set("limit", String(p.limit ?? 50));
    return request<DocumentPage>(`/orgs/${orgId}/documents?${qs.toString()}`);
  },
  upload: (orgId: string, collectionId: string, files: File[]) => {
    const body = new FormData();
    body.append("collection_id", collectionId);
    for (const file of files) body.append("files", file);
    return request<UploadResult[]>(`/orgs/${orgId}/documents`, { method: "POST", body });
  },
  remove: (orgId: string, id: string) => request<void>(`/orgs/${orgId}/documents/${id}`, { method: "DELETE" }),
  summary: (orgId: string) => request<StatusSummary>(`/orgs/${orgId}/documents/summary`),
  pages: (orgId: string, id: string) => request<PageInfo[]>(`/orgs/${orgId}/documents/${id}/pages`),
  reprocess: (orgId: string, id: string) =>
    request<{ status: string }>(`/orgs/${orgId}/documents/${id}/reprocess`, { method: "POST" }),
  /** Server-sent events; the API re-authorizes every event for this caller. */
  eventsUrl: (orgId: string) => `${BASE}/orgs/${orgId}/documents/events`,
  /** Same-origin URL; the API re-checks the caller's access on every request. */
  fileUrl: (orgId: string, id: string, download = false) =>
    `${BASE}/orgs/${orgId}/documents/${id}/file${download ? "?download=true" : ""}`,
};
