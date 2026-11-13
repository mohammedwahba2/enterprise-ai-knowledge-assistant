const KEY = "ka_invite";
const PATTERN = /^#token=([A-Za-z0-9_-]{20,200})$/;

/**
 * The invitation link carries its token in the URL fragment (never sent to servers or logs).
 * Visitors who are not signed in must go through sign-in first, which would drop the fragment,
 * so the token is parked in sessionStorage (tab-scoped) and the address bar is scrubbed.
 */
export function takeInviteToken(): string | null {
  const hash = window.location.hash;
  if (hash) {
    const match = PATTERN.exec(hash);
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    if (match?.[1]) {
      try {
        window.sessionStorage.setItem(KEY, match[1]);
      } catch {
        return match[1]; // storage unavailable: still usable for this page view
      }
      return match[1];
    }
    return null;
  }
  try {
    return window.sessionStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function clearInviteToken(): void {
  try {
    window.sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
