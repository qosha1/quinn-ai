import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const publicPaths = ["/login", "/register", "/forgot-password", "/reset-password"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Check if accessing public path
  const isPublicPath = publicPaths.some((path) => pathname.startsWith(path));

  // Get token from cookie or authorization header
  const token = request.cookies.get("access_token")?.value;

  // For localStorage-based auth, we check for a special cookie that indicates
  // the user has a token (set by client-side JavaScript)
  const hasAuthCookie = request.cookies.get("has_auth")?.value === "true";

  const isAuthenticated = !!token || hasAuthCookie;

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
