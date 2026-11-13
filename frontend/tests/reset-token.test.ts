import { afterEach, describe, expect, it, vi } from "vitest";
import { takeTokenFromHash } from "@/lib/resetToken";

function stubLocation(hash: string) {
  const replaceState = vi.fn();
  vi.stubGlobal("window", {
    location: { hash, pathname: "/en/reset-password", search: "" },
    history: { replaceState },
  });
  return replaceState;
}
afterEach(() => vi.unstubAllGlobals());

describe("takeTokenFromHash", () => {
  it("returns the token and scrubs the fragment from history", () => {
    const token = "a".repeat(43);
    const replace = stubLocation(`#token=${token}`);
    expect(takeTokenFromHash()).toBe(token);
    expect(replace).toHaveBeenCalledWith(null, "", "/en/reset-password");
  });
  it("rejects malformed fragments but still scrubs them", () => {
    const replace = stubLocation("#token=short");
    expect(takeTokenFromHash()).toBeNull();
    expect(replace).toHaveBeenCalled();
    stubLocation("#token=" + "a".repeat(43) + "&x=1");
    expect(takeTokenFromHash()).toBeNull();
  });
  it("handles a missing fragment", () => {
    const replace = stubLocation("");
    expect(takeTokenFromHash()).toBeNull();
    expect(replace).not.toHaveBeenCalled();
  });
});
