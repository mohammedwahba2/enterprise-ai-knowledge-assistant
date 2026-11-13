import createMiddleware from "next-intl/middleware";
import { NextResponse, type NextRequest } from "next/server";
import { routing } from "./i18n/routing";

const intl = createMiddleware(routing);

// accept-invite is public so the fragment token survives; the page itself requires a session.
const PUBLIC_PATHS = new Set(["/sign-in", "/sign-up", "/forgot-password", "/reset-password", "/accept-invite"]);
const LOCALE_PATH = /^\/(en|ar)(\/.*)?$/;

/**
 * Cheap, optimistic redirect: no `ka_session` hint cookie means "certainly not signed in".
 * The hint is not a credential and is not trusted for anything else; the API decides access.
 */
export default function proxy(req: NextRequest) {
  const match = LOCALE_PATH.exec(req.nextUrl.pathname);
  if (match) {
    const [, locale, rest = "/"] = match;
    const path = rest.replace(/\/+$/, "") || "/";
    if (!PUBLIC_PATHS.has(path) && !req.cookies.has("ka_session")) {
      const url = req.nextUrl.clone();
      url.pathname = `/${locale}/sign-in`;
      url.search = path === "/" ? "" : `?next=${encodeURIComponent(path)}`;
      return NextResponse.redirect(url);
    }
  }
  return intl(req);
}

export const config = {
  // Everything except API, Next internals and files with an extension.
  matcher: ["/((?!api|_next|.*\\..*).*)"],
};
