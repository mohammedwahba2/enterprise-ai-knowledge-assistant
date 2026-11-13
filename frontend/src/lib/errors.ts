import { ApiError } from "./api";

export type ErrorView = { key: string; values?: Record<string, string>; reasons: string[] };

/** Map an API failure to message keys in the `Errors` namespace. Never show raw server text. */
export function describeError(e: unknown): ErrorView {
  if (!(e instanceof ApiError)) return { key: "UNKNOWN", reasons: [] };
  switch (e.code) {
    case "RATE_LIMITED": {
      const minutes = Math.max(1, Math.ceil((e.retryAfter ?? 60) / 60));
      return { key: "RATE_LIMITED", values: { minutes: String(minutes) }, reasons: [] };
    }
    case "WEAK_PASSWORD":
      return { key: "WEAK_PASSWORD", reasons: e.problem.reasons ?? [] };
    case "INVALID_CREDENTIALS":
    case "EMAIL_TAKEN":
    case "INVALID_TOKEN":
    case "VALIDATION_ERROR":
    case "CSRF_FAILED":
    case "NETWORK":
    case "SERVICE_UNAVAILABLE":
    case "INVALID_INVITATION":
    case "ORG_LIMIT_REACHED":
    case "FORBIDDEN":
    case "NOT_FOUND":
      return { key: e.code, reasons: [] };
    default:
      return { key: "UNKNOWN", reasons: [] };
  }
}
