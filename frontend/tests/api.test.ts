import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, auth, readCookie, request } from "@/lib/api";
import { describeError } from "@/lib/errors";
import { PASSWORD_MAX, PASSWORD_MIN, passwordLengthOk } from "@/lib/passwordPolicy";
import { safeNext } from "@/lib/redirect";

type Call = { url: string; method: string; headers: Headers };
let calls: Call[];
let queue: Response[];

const problem = (status: number, code: string, headers: Record<string, string> = {}) =>
  new Response(JSON.stringify({ code }), {
    status,
    headers: { "content-type": "application/problem+json", ...headers },
  });
const ok = (body: unknown = {}) => new Response(JSON.stringify(body), { status: 200 });

beforeEach(() => {
  calls = [];
  queue = [];
  vi.stubGlobal("document", { cookie: "ka_csrf=tok123; other=1" });
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit) => {
      calls.push({ url, method: String(init.method), headers: new Headers(init.headers) });
      const next = queue.shift();
      if (!next) throw new Error("unexpected fetch");
      return next;
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

describe("csrf + cookies", () => {
  it("reads cookies by name", () => {
    expect(readCookie("ka_csrf")).toBe("tok123");
    expect(readCookie("missing")).toBe("");
  });
  it("sends the CSRF header on unsafe methods only", async () => {
    queue.push(ok(), ok());
    await request("/x", { method: "POST", body: "{}" });
    await request("/x");
    expect(calls[0]!.headers.get("x-csrf-token")).toBe("tok123");
    expect(calls[1]!.headers.get("x-csrf-token")).toBeNull();
  });
  it("sets JSON content type when a body is present", async () => {
    queue.push(ok());
    await request("/x", { method: "POST", body: "{}" });
    expect(calls[0]!.headers.get("content-type")).toBe("application/json");
  });
});

describe("error handling", () => {
  it("turns problem+json into ApiError with code and Retry-After", async () => {
    queue.push(problem(429, "RATE_LIMITED", { "retry-after": "120" }));
    const err = await request("/x").catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 429, code: "RATE_LIMITED", retryAfter: 120 });
  });
  it("maps network failure to NETWORK", async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockRejectedValueOnce(new TypeError("fail"));
    await expect(request("/x")).rejects.toMatchObject({ code: "NETWORK" });
  });
  it("tolerates non-JSON error bodies", async () => {
    queue.push(new Response("<html>bad gateway</html>", { status: 502 }));
    await expect(request("/x")).rejects.toMatchObject({ status: 502, code: "UNKNOWN" });
  });
  it("describeError never exposes server text and rounds retry-after up to minutes", () => {
    const e = new ApiError(429, "RATE_LIMITED", { title: "secret detail" }, 61);
    expect(describeError(e)).toEqual({ key: "RATE_LIMITED", values: { minutes: "2" }, reasons: [] });
    expect(describeError(new ApiError(500, "SOMETHING_NEW")).key).toBe("UNKNOWN");
    expect(describeError(new Error("boom")).key).toBe("UNKNOWN");
    expect(describeError(new ApiError(422, "WEAK_PASSWORD", { reasons: ["TOO_SHORT"] })).reasons).toEqual(["TOO_SHORT"]);
  });
});

describe("refresh-and-retry", () => {
  it("refreshes once on 401 UNAUTHENTICATED then retries the original call", async () => {
    queue.push(problem(401, "UNAUTHENTICATED"), ok({ id: "u" }), ok({ hello: 1 }));
    const result = await request<{ hello: number }>("/me");
    expect(result.hello).toBe(1);
    expect(calls.map((c) => c.url)).toEqual(["/api/v1/me", "/api/v1/auth/refresh", "/api/v1/me"]);
  });
  it("does not loop: a second 401 after a successful refresh surfaces", async () => {
    queue.push(problem(401, "UNAUTHENTICATED"), ok(), problem(401, "UNAUTHENTICATED"));
    await expect(request("/me")).rejects.toMatchObject({ code: "UNAUTHENTICATED" });
    expect(calls).toHaveLength(3);
  });
  it("surfaces the original error when refresh fails", async () => {
    queue.push(problem(401, "UNAUTHENTICATED"), problem(401, "SESSION_INVALID"));
    await expect(request("/me")).rejects.toMatchObject({ code: "UNAUTHENTICATED" });
    expect(calls).toHaveLength(2);
  });
  it("treats REFRESH_RACE as success (a sibling tab just rotated)", async () => {
    queue.push(problem(401, "UNAUTHENTICATED"), problem(401, "REFRESH_RACE"), ok({ ok: 1 }));
    await expect(request("/me")).resolves.toEqual({ ok: 1 });
  });
  it("coalesces concurrent 401s into one refresh", async () => {
    // two failing calls, one refresh, two retries
    queue.push(problem(401, "UNAUTHENTICATED"), problem(401, "UNAUTHENTICATED"), ok(), ok({ n: 1 }), ok({ n: 2 }));
    const [a, b] = await Promise.all([request("/a"), request("/b")]);
    expect([a, b]).toEqual([{ n: 1 }, { n: 2 }]);
    expect(calls.filter((c) => c.url.endsWith("/auth/refresh"))).toHaveLength(1);
  });
  it("auth endpoints never trigger a refresh", async () => {
    queue.push(problem(401, "UNAUTHENTICATED"));
    await expect(auth.signIn("a@b.co", "pw")).rejects.toMatchObject({ status: 401 });
    expect(calls).toHaveLength(1);
  });
  it("sign-out does not try to refresh on 401", async () => {
    queue.push(problem(401, "UNAUTHENTICATED"));
    await expect(auth.signOut()).rejects.toBeInstanceOf(ApiError);
    expect(calls).toHaveLength(1);
  });
});

describe("helpers", () => {
  it("password length mirrors the server (code points, NFKC)", () => {
    expect(passwordLengthOk("x".repeat(PASSWORD_MIN - 1))).toBe(false);
    expect(passwordLengthOk("x".repeat(PASSWORD_MIN))).toBe(true);
    expect(passwordLengthOk("x".repeat(PASSWORD_MAX + 1))).toBe(false);
    expect(passwordLengthOk("كلمة-مرور-طويلة")).toBe(true);
    expect(passwordLengthOk("😀".repeat(PASSWORD_MIN))).toBe(true); // 10 code points
  });
  it("safeNext only allows same-site relative paths", () => {
    expect(safeNext("/library")).toBe("/library");
    expect(safeNext(null)).toBe("/");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil", "javascript:alert(1)", "library"]) {
      expect(safeNext(bad)).toBe("/");
    }
  });
});
