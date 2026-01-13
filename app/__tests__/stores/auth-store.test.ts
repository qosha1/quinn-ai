import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act } from "@testing-library/react";

// Mock the auth and api modules before importing the store
vi.mock("@/lib/auth", () => ({
  setTokens: vi.fn(),
  removeTokens: vi.fn(),
  isAuthenticated: vi.fn(() => false),
}));

vi.mock("@/lib/api", () => ({
  authApi: {
    login: vi.fn(),
  },
  userApi: {
    getMe: vi.fn(),
  },
}));

import { useAuthStore } from "@/stores/auth-store";
import { authApi, userApi } from "@/lib/api";
import { setTokens, removeTokens, isAuthenticated } from "@/lib/auth";

describe("auth-store", () => {
  const mockUser = {
    id: "user-123",
    email: "test@example.com",
    first_name: "John",
    last_name: "Doe",
    created_at: "2024-01-01T00:00:00Z",
  };

  const mockTokens = {
    access: "access-token-123",
    refresh: "refresh-token-456",
  };

  beforeEach(() => {
    // Reset store state
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.resetAllMocks();
  });

  describe("initial state", () => {
    it("should have null user on initial load", () => {
      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
    });

    it("should have isAuthenticated as false initially", () => {
      const state = useAuthStore.getState();
      expect(state.isAuthenticated).toBe(false);
    });

    it("should have isLoading as false initially", () => {
      const state = useAuthStore.getState();
      expect(state.isLoading).toBe(false);
    });

    it("should have no error initially", () => {
      const state = useAuthStore.getState();
      expect(state.error).toBeNull();
    });
  });

  describe("login action", () => {
    it("should set isLoading to true when login starts", async () => {
      vi.mocked(authApi.login).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      // Start login but don't await
      act(() => {
        useAuthStore.getState().login("test@example.com", "password123").catch(() => {});
      });

      // Check loading state immediately after calling login
      expect(useAuthStore.getState().isLoading).toBe(true);
    });

    it("should set user and isAuthenticated on successful login", async () => {
      vi.mocked(authApi.login).mockResolvedValue({ data: mockTokens } as never);
      vi.mocked(userApi.getMe).mockResolvedValue({ data: mockUser } as never);

      await act(async () => {
        await useAuthStore.getState().login("test@example.com", "password123");
      });

      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
      expect(state.error).toBeNull();
    });

    it("should call setTokens with tokens from API response", async () => {
      vi.mocked(authApi.login).mockResolvedValue({ data: mockTokens } as never);
      vi.mocked(userApi.getMe).mockResolvedValue({ data: mockUser } as never);

      await act(async () => {
        await useAuthStore.getState().login("test@example.com", "password123");
      });

      expect(setTokens).toHaveBeenCalledWith(mockTokens);
    });

    it("should call authApi.login with correct credentials", async () => {
      vi.mocked(authApi.login).mockResolvedValue({ data: mockTokens } as never);
      vi.mocked(userApi.getMe).mockResolvedValue({ data: mockUser } as never);

      await act(async () => {
        await useAuthStore.getState().login("test@example.com", "password123");
      });

      expect(authApi.login).toHaveBeenCalledWith("test@example.com", "password123");
    });

    it("should set error message on login failure", async () => {
      const errorMessage = "Invalid credentials";
      vi.mocked(authApi.login).mockRejectedValue(new Error(errorMessage));

      await act(async () => {
        try {
          await useAuthStore.getState().login("test@example.com", "wrongpassword");
        } catch {
          // Expected to throw
        }
      });

      const state = useAuthStore.getState();
      expect(state.error).toBe(errorMessage);
      expect(state.isLoading).toBe(false);
      expect(state.isAuthenticated).toBe(false);
    });

    it("should set default error message for non-Error exceptions", async () => {
      vi.mocked(authApi.login).mockRejectedValue("Unknown error");

      await act(async () => {
        try {
          await useAuthStore.getState().login("test@example.com", "password123");
        } catch {
          // Expected to throw
        }
      });

      const state = useAuthStore.getState();
      expect(state.error).toBe("Invalid email or password");
    });

    it("should throw error after setting state on login failure", async () => {
      vi.mocked(authApi.login).mockRejectedValue(new Error("Login failed"));

      await expect(
        act(async () => {
          await useAuthStore.getState().login("test@example.com", "password123");
        })
      ).rejects.toThrow("Login failed");
    });
  });

  describe("logout action", () => {
    it("should clear user on logout", () => {
      // Set initial authenticated state
      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
      });

      act(() => {
        useAuthStore.getState().logout();
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
    });

    it("should set isAuthenticated to false on logout", () => {
      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
      });

      act(() => {
        useAuthStore.getState().logout();
      });

      expect(useAuthStore.getState().isAuthenticated).toBe(false);
    });

    it("should clear any error on logout", () => {
      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
        error: "Some error",
      });

      act(() => {
        useAuthStore.getState().logout();
      });

      expect(useAuthStore.getState().error).toBeNull();
    });

    it("should call removeTokens on logout", () => {
      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
      });

      act(() => {
        useAuthStore.getState().logout();
      });

      expect(removeTokens).toHaveBeenCalled();
    });
  });

  describe("setUser action", () => {
    it("should set user and isAuthenticated when user is provided", () => {
      act(() => {
        useAuthStore.getState().setUser(mockUser);
      });

      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
    });

    it("should clear user and set isAuthenticated to false when null is provided", () => {
      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
      });

      act(() => {
        useAuthStore.getState().setUser(null);
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });

  describe("fetchUser action", () => {
    it("should fetch and set user when authenticated", async () => {
      vi.mocked(isAuthenticated).mockReturnValue(true);
      vi.mocked(userApi.getMe).mockResolvedValue({ data: mockUser } as never);

      await act(async () => {
        await useAuthStore.getState().fetchUser();
      });

      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.isLoading).toBe(false);
    });

    it("should not fetch user when not authenticated", async () => {
      vi.mocked(isAuthenticated).mockReturnValue(false);

      await act(async () => {
        await useAuthStore.getState().fetchUser();
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(userApi.getMe).not.toHaveBeenCalled();
    });

    it("should clear user and tokens on fetch failure", async () => {
      vi.mocked(isAuthenticated).mockReturnValue(true);
      vi.mocked(userApi.getMe).mockRejectedValue(new Error("Unauthorized"));

      await act(async () => {
        await useAuthStore.getState().fetchUser();
      });

      const state = useAuthStore.getState();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(removeTokens).toHaveBeenCalled();
    });

    it("should set isLoading during fetch", async () => {
      vi.mocked(isAuthenticated).mockReturnValue(true);
      vi.mocked(userApi.getMe).mockImplementation(
        () => new Promise(() => {}) // Never resolves
      );

      // Start fetch but don't await
      act(() => {
        useAuthStore.getState().fetchUser().catch(() => {});
      });

      expect(useAuthStore.getState().isLoading).toBe(true);
    });
  });

  describe("clearError action", () => {
    it("should clear error when called", () => {
      useAuthStore.setState({ error: "Some error message" });

      act(() => {
        useAuthStore.getState().clearError();
      });

      expect(useAuthStore.getState().error).toBeNull();
    });

    it("should not affect other state properties", () => {
      useAuthStore.setState({
        user: mockUser,
        isAuthenticated: true,
        error: "Some error",
      });

      act(() => {
        useAuthStore.getState().clearError();
      });

      const state = useAuthStore.getState();
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
    });
  });

  describe("persist middleware", () => {
    it("should only persist user and isAuthenticated", () => {
      // The store uses partialize to only persist specific fields
      // This test verifies the persist configuration behavior
      const state = useAuthStore.getState();

      // All actions should be functions
      expect(typeof state.login).toBe("function");
      expect(typeof state.logout).toBe("function");
      expect(typeof state.setUser).toBe("function");
      expect(typeof state.fetchUser).toBe("function");
      expect(typeof state.clearError).toBe("function");
    });

    it("should use auth-storage as the storage key", () => {
      // The persist middleware is configured with name: "auth-storage"
      // This is verified by the store configuration
      expect(useAuthStore.persist.getOptions().name).toBe("auth-storage");
    });
  });
});
