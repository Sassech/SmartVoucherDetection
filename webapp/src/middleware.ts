/**
 * Route protection middleware — R-33, S-17, S-18, S-19.
 *
 * Checks for the `refresh_token` HttpOnly cookie (set by FastAPI login).
 * - No cookie → redirect to /login (S-17)
 * - Cookie present → pass through (S-18)
 * - /login is always public (S-19)
 * - /api/*, /_next/*, /favicon* bypass matcher entirely (see config.matcher)
 */

import { type NextRequest, NextResponse } from "next/server";

export function middleware(request: NextRequest): NextResponse {
  const refreshCookie = request.cookies.get("refresh_token");

  if (!refreshCookie?.value) {
    const loginUrl = new URL("/login", request.url);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  // Protect all routes EXCEPT: /login, /_next/*, /favicon*, /api/*
  matcher: ["/((?!login|_next|favicon|api).*)"],
};
