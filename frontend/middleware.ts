import { NextResponse, type NextRequest } from "next/server";

// A first, cheap gate: no session cookie means the sign-in page. The API still checks the session
// itself on every request and answers 401 when it is invalid or expired.
const PUBLIC = ["/login", "/register"];

export function middleware(req: NextRequest) {
  const { pathname, search } = req.nextUrl;
  const hasSession = req.cookies.has("agentrank_session");
  const isPublic = PUBLIC.includes(pathname);

  if (!hasSession && !isPublic) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.search = pathname === "/" ? "" : `?next=${encodeURIComponent(pathname + search)}`;
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  // Everything except the API proxy, stored evidence, Next internals and static files.
  matcher: ["/((?!api|storage|_next|favicon.ico|.*\\.[a-z]+$).*)"],
};
