import { describe, it, expect, vi, beforeEach } from "vitest";
import { NextRequest, NextResponse } from "next/server";
import { middleware, config } from "@/middleware";

// Mock NextResponse
vi.mock("next/server", async () => {
  const actual = await vi.importActual("next/server");
  return {
    ...actual,
    NextResponse: {
      redirect: vi.fn((url: URL) => ({
        type: "redirect",
        url: url.toString(),
      })),
      next: vi.fn(() => ({
        type: "next",
      })),
    },
  };
});

// Helper to create mock NextRequest
function createMockRequest(
  pathname: string,
  options: {
    accessToken?: string;
    hasAuth?: string;
  } = {}
): NextRequest {
  const url = new URL(pathname, "http://localhost:3000");

  const cookies = new Map<string, { value: string }>();
  if (options.accessToken) {
    cookies.set("access_token", { value: options.accessToken });
  }
  if (options.hasAuth) {
    cookies.set("has_auth", { value: options.hasAuth });
  }

  return {
    nextUrl: url,
    url: url.toString(),
    cookies: {
      get: (name: string) => cookies.get(name),
      getAll: () => Array.from(cookies.entries()).map(([name, { value }]) => ({ name, value })),
      has: (name: string) => cookies.has(name),
      set: vi.fn(),
      delete: vi.fn(),
    },
  } as unknown as NextRequest;
}

describe("Middleware", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("public paths", () => {
    const publicPaths = ["/login", "/register", "/forgot-password", "/reset-password"];

    publicPaths.forEach((path) => {
      it(`should allow unauthenticated access to ${path}`, () => {
        const request = createMockRequest(path);

        middleware(request);

        expect(NextResponse.next).toHaveBeenCalled();
        expect(NextResponse.redirect).not.toHaveBeenCalled();
      });
    });

    it("should allow access to /login/callback (nested public path)", () => {
      const request = createMockRequest("/login/callback");

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });

    it("should allow access to /register?plan=pro (with query params)", () => {
      const request = createMockRequest("/register?plan=pro");

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });
  });

  describe("protected paths", () => {
    it("should redirect unauthenticated user from / to /login", () => {
      const request = createMockRequest("/");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/login");
    });

    it("should redirect unauthenticated user from /dashboard to /login", () => {
      const request = createMockRequest("/dashboard");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/login");
    });

    it("should redirect unauthenticated user from /team to /login", () => {
      const request = createMockRequest("/team");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/login");
    });

    it("should redirect unauthenticated user from /billing to /login", () => {
      const request = createMockRequest("/billing");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
    });

    it("should redirect unauthenticated user from /settings to /login", () => {
      const request = createMockRequest("/settings");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
    });
  });

  describe("authenticated users", () => {
    it("should allow authenticated user (with access_token cookie) to access /", () => {
      const request = createMockRequest("/", { accessToken: "valid-token" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
      expect(NextResponse.redirect).not.toHaveBeenCalled();
    });

    it("should allow authenticated user (with has_auth cookie) to access /", () => {
      const request = createMockRequest("/", { hasAuth: "true" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
      expect(NextResponse.redirect).not.toHaveBeenCalled();
    });

    it("should allow authenticated user to access /dashboard", () => {
      const request = createMockRequest("/dashboard", { accessToken: "valid-token" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });

    it("should allow authenticated user to access /team/members", () => {
      const request = createMockRequest("/team/members", { hasAuth: "true" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });

    it("should allow authenticated user to access /billing/invoices", () => {
      const request = createMockRequest("/billing/invoices", { accessToken: "token" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });

    it("should allow authenticated user to access /settings/profile", () => {
      const request = createMockRequest("/settings/profile", { hasAuth: "true" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });
  });

  describe("redirect authenticated users from auth pages", () => {
    it("should redirect authenticated user from /login to /", () => {
      const request = createMockRequest("/login", { accessToken: "valid-token" });

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/");
    });

    it("should redirect authenticated user from /register to /", () => {
      const request = createMockRequest("/register", { hasAuth: "true" });

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/");
    });

    it("should redirect authenticated user from /forgot-password to /", () => {
      const request = createMockRequest("/forgot-password", { accessToken: "token" });

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/");
    });
  });

  describe("return URL preservation", () => {
    it("should preserve returnUrl when redirecting to login", () => {
      const request = createMockRequest("/dashboard/settings");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.pathname).toBe("/login");
      expect(redirectCall.searchParams.get("returnUrl")).toBe("/dashboard/settings");
    });

    it("should preserve returnUrl for nested paths", () => {
      const request = createMockRequest("/team/members/invite");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.searchParams.get("returnUrl")).toBe("/team/members/invite");
    });

    it("should not set returnUrl when redirecting from root /", () => {
      const request = createMockRequest("/");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
      const redirectCall = vi.mocked(NextResponse.redirect).mock.calls[0][0] as URL;
      expect(redirectCall.searchParams.has("returnUrl")).toBe(false);
    });
  });

  describe("has_auth cookie value", () => {
    it("should consider has_auth=true as authenticated", () => {
      const request = createMockRequest("/dashboard", { hasAuth: "true" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });

    it("should consider has_auth=false as not authenticated", () => {
      const request = createMockRequest("/dashboard", { hasAuth: "false" });

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
    });

    it("should consider empty has_auth as not authenticated", () => {
      const request = createMockRequest("/dashboard", { hasAuth: "" });

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
    });
  });

  describe("config matcher", () => {
    it("should have correct matcher configuration", () => {
      expect(config.matcher).toBeDefined();
      expect(Array.isArray(config.matcher)).toBe(true);
    });

    it("should exclude api routes from matching", () => {
      // The matcher pattern excludes 'api' routes
      const pattern = config.matcher[0];
      expect(pattern).toContain("(?!api");
    });

    it("should exclude _next/static from matching", () => {
      const pattern = config.matcher[0];
      expect(pattern).toContain("_next/static");
    });

    it("should exclude _next/image from matching", () => {
      const pattern = config.matcher[0];
      expect(pattern).toContain("_next/image");
    });

    it("should exclude favicon.ico from matching", () => {
      const pattern = config.matcher[0];
      expect(pattern).toContain("favicon.ico");
    });
  });

  describe("edge cases", () => {
    it("should handle requests without cookies", () => {
      const request = createMockRequest("/dashboard");

      expect(() => middleware(request)).not.toThrow();
    });

    it("should handle deeply nested protected paths", () => {
      const request = createMockRequest("/settings/security/two-factor/setup");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
    });

    it("should handle paths with special characters", () => {
      const request = createMockRequest("/team/user%40example.com");

      middleware(request);

      expect(NextResponse.redirect).toHaveBeenCalled();
    });

    it("should prioritize access_token over has_auth", () => {
      const request = createMockRequest("/dashboard", {
        accessToken: "valid-token",
        hasAuth: "false", // Even with has_auth=false, access_token should win
      });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });
  });

  describe("authentication checks", () => {
    it("should treat any truthy access_token as authenticated", () => {
      const request = createMockRequest("/dashboard", { accessToken: "any-value" });

      middleware(request);

      expect(NextResponse.next).toHaveBeenCalled();
    });

    it("should only treat has_auth=true as authenticated", () => {
      const request = createMockRequest("/dashboard", { hasAuth: "TRUE" }); // Case matters

      middleware(request);

      // "TRUE" !== "true", so should redirect
      expect(NextResponse.redirect).toHaveBeenCalled();
    });
  });
});
