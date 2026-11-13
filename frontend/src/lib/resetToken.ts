/** Reads `#token=...` and immediately strips it from the address bar and history entry. */
export function takeTokenFromHash(): string | null {
  const hash = window.location.hash;
  const match = /^#token=([A-Za-z0-9_-]{20,200})$/.exec(hash);
  if (hash) window.history.replaceState(null, "", window.location.pathname + window.location.search);
  return match ? (match[1] ?? null) : null;
}
