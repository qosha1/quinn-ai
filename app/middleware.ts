import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const publicPaths = ["/login", "/register", "/forgot-password", "/reset-password"];

function isTokenExpired(token: string): boolean {
  try {
    // JWT tokens are base64url encoded: header.payload.signature
    const parts = token.split(".");
    if (parts.length !== 3) return true;

    // Decode payload (base64url)
    const payload = JSON.parse(
      Buffer.from(parts[1].replace(/-/g, "+").replace(/_/g, "/"), "base64").toString()
    );

    // Check exp claim
    if (!payload.exp) return false; // No expiry = treat as valid
    return Date.now() >= payload.exp * 1000;
  } catch {
    return true; // Malformed token = expired
  }
}

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Check if accessing public path
  const isPublicPath = publicPaths.some((path) => pathname.startsWith(path));

  // Get token from cookie
  const token = request.cookies.get("access_token")?.value;

  // Validate token if present
  let isAuthenticated = false;
  if (token && !isTokenExpired(token)) {
    isAuthenticated = true;
  } else if (token && isTokenExpired(token)) {
    // Token expired - clear cookies and redirect to login
    if (!isPublicPath) {
      const response = NextResponse.redirect(new URL("/login", request.url));
      response.cookies.delete("access_token");
      response.cookies.delete("has_auth");
      return response;
    }
  }

  // has_auth cookie is supplementary signal only (for localStorage-based auth)
  // It's not sufficient alone but indicates client has a token
  if (!isAuthenticated) {
    const hasAuthCookie = request.cookies.get("has_auth")?.value === "true";
    if (hasAuthCookie) {
      isAuthenticated = true;
    }
  }

  // Redirect authenticated users away from auth pages
  if (isPublicPath && isAuthenticated) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // Redirect unauthenticated users to login
  if (!isPublicPath && !isAuthenticated) {
    const loginUrl = new URL("/login", request.url);

    // Preserve the original URL as return URL
    if (pathname !== "/") {
      loginUrl.searchParams.set("returnUrl", pathname);
    }

    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    /*
     * Match all request paths except:
     * - api (API routes)
     * - _next/static (static files)
     * - _next/image (image optimization files)
     * - favicon.ico (favicon file)
     * - public folder files
     */
    "/((?!api|_next/static|_next/image|favicon.ico|.*\\..*|_next).*)",
  ],
};
