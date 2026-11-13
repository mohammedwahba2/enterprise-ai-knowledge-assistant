import { afterEach, describe, expect, it, vi } from "vitest";
import { clearInviteToken, takeInviteToken } from "@/lib/inviteToken";
import { pickOrg, recallOrg, rememberOrg } from "@/lib/orgs";
import type { Org } from "@/lib/api";

const org = (slug: string): Org => ({ id: slug, name: slug, slug, role: "member" });

describe("pickOrg", () => {
  it("prefers the last-used workspace when it is still accessible", () => {
    expect(pickOrg([org("a"), org("b")], "b")?.slug).toBe("b");
  });
  it("falls back to the first workspace when the remembered one is gone (e.g. removed)", () => {
    expect(pickOrg([org("a"), org("b")], "zzz")?.slug).toBe("a");
    expect(pickOrg([org("a")], null)?.slug).toBe("a");
  });
  it("returns null when the user has no workspace", () => {
    expect(pickOrg([], "a")).toBeNull();
  });
});

describe("last-workspace memory", () => {
  it("is stored per user so another account on the same browser never inherits it", () => {
    const local = new Map<string, string>();
    vi.stubGlobal("window", {
      localStorage: { getItem: (k: string) => local.get(k) ?? null, setItem: (k: string, v: string) => void local.set(k, v) },
    });
    rememberOrg("user-1", "acme");
    expect(recallOrg("user-1")).toBe("acme");
    expect(recallOrg("user-2")).toBeNull();
    vi.unstubAllGlobals();
  });
  it("tolerates blocked storage", () => {
    vi.stubGlobal("window", {
      localStorage: { getItem: () => { throw new Error("denied"); }, setItem: () => { throw new Error("denied"); } },
    });
    expect(() => rememberOrg("u", "a")).not.toThrow();
    expect(recallOrg("u")).toBeNull();
    vi.unstubAllGlobals();
  });
});

function stubBrowser(hash: string, stored: string | null = null, storageWorks = true) {
  const store = new Map<string, string>(stored ? [["ka_invite", stored]] : []);
  const replaceState = vi.fn();
  vi.stubGlobal("window", {
    location: { hash, pathname: "/en/accept-invite", search: "" },
    history: { replaceState },
    sessionStorage: storageWorks
      ? {
          getItem: (k: string) => store.get(k) ?? null,
          setItem: (k: string, v: string) => void store.set(k, v),
          removeItem: (k: string) => void store.delete(k),
        }
      : {
          getItem: () => {
            throw new Error("denied");
          },
          setItem: () => {
            throw new Error("denied");
          },
          removeItem: () => {
            throw new Error("denied");
          },
        },
  });
  return { store, replaceState };
}
afterEach(() => vi.unstubAllGlobals());

describe("invitation token handling", () => {
  const token = "b".repeat(43);
  it("takes the token from the fragment, parks it for the sign-in detour and scrubs the URL", () => {
    const { store, replaceState } = stubBrowser(`#token=${token}`);
    expect(takeInviteToken()).toBe(token);
    expect(store.get("ka_invite")).toBe(token);
    expect(replaceState).toHaveBeenCalledWith(null, "", "/en/accept-invite");
  });
  it("recovers the parked token after the redirect back from sign-in", () => {
    stubBrowser("", token);
    expect(takeInviteToken()).toBe(token);
  });
  it("rejects malformed fragments (but still scrubs them)", () => {
    for (const bad of ["#token=short", `#token=${token}&x=1`, `#other=${token}`, `#token=${token}<script>`]) {
      const { store, replaceState } = stubBrowser(bad);
      expect(takeInviteToken()).toBeNull();
      expect(store.has("ka_invite")).toBe(false);
      expect(replaceState).toHaveBeenCalled();
    }
  });
  it("still works for this page view when storage is blocked", () => {
    stubBrowser(`#token=${token}`, null, false);
    expect(takeInviteToken()).toBe(token);
    expect(() => clearInviteToken()).not.toThrow();
  });
  it("clears the parked token after use", () => {
    const { store } = stubBrowser("", token);
    clearInviteToken();
    expect(store.has("ka_invite")).toBe(false);
  });
});
