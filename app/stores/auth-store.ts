import { create } from "zustand";
import { persist } from "zustand/middleware";
import { User, userApi, authApi } from "@/lib/api";
import { setTokens, removeTokens, isAuthenticated as checkAuth } from "@/lib/auth";

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  error: string | null;

  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setUser: (user: User | null) => void;
  fetchUser: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,

      login: async (email: string, password: string) => {
        set({ isLoading: true, error: null });
        try {
          const tokenResponse = await authApi.login(email, password);
          setTokens(tokenResponse.data);

          const userResponse = await userApi.getMe();
          set({
            user: userResponse.data,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch (error: unknown) {
          const message =
            error instanceof Error
              ? error.message
              : "Invalid email or password";
          set({ error: message, isLoading: false });
          throw error;
        }
      },

      logout: () => {
        removeTokens();
        set({ user: null, isAuthenticated: false, error: null });
      },

      setUser: (user: User | null) => {
        set({ user, isAuthenticated: !!user });
      },

      fetchUser: async () => {
        if (!checkAuth()) {
          set({ user: null, isAuthenticated: false });
          return;
        }

        set({ isLoading: true });
        try {
          const response = await userApi.getMe();
          set({
            user: response.data,
            isAuthenticated: true,
            isLoading: false,
          });
        } catch {
          removeTokens();
          set({ user: null, isAuthenticated: false, isLoading: false });
        }
      },

      clearError: () => {
        set({ error: null });
      },
    }),
    {
      name: "auth-storage",
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    }
  )
);
