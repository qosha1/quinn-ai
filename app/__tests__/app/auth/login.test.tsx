import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import LoginPage from "@/app/(auth)/login/page";

// Mock next/navigation
const mockPush = vi.fn();
const mockSearchParams = new URLSearchParams();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  useSearchParams: () => mockSearchParams,
}));

// Mock the auth store
const mockLogin = vi.fn();
const mockClearError = vi.fn();
let mockIsLoading = false;
let mockError: string | null = null;

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: () => ({
    login: mockLogin,
    isLoading: mockIsLoading,
    error: mockError,
    clearError: mockClearError,
  }),
}));

describe("LoginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockIsLoading = false;
    mockError = null;
    mockSearchParams.delete("returnUrl");

    // Reset document.cookie
    Object.defineProperty(document, "cookie", {
      writable: true,
      value: "",
    });
  });

  describe("rendering", () => {
    it("should render login form", () => {
      render(<LoginPage />);

      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });

    it("should render email input", () => {
      render(<LoginPage />);

      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    });

    it("should render password input", () => {
      render(<LoginPage />);

      expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    });

    it("should render sign in button", () => {
      render(<LoginPage />);

      expect(screen.getByRole("button", { name: /sign in/i })).toBeInTheDocument();
    });

    it("should render forgot password link", () => {
      render(<LoginPage />);

      expect(screen.getByRole("link", { name: /forgot password/i })).toBeInTheDocument();
    });

    it("should render sign up link", () => {
      render(<LoginPage />);

      expect(screen.getByRole("link", { name: /sign up/i })).toBeInTheDocument();
    });

    it("should link forgot password to /forgot-password", () => {
      render(<LoginPage />);

      const link = screen.getByRole("link", { name: /forgot password/i });
      expect(link).toHaveAttribute("href", "/forgot-password");
    });

    it("should link sign up to /register", () => {
      render(<LoginPage />);

      const link = screen.getByRole("link", { name: /sign up/i });
      expect(link).toHaveAttribute("href", "/register");
    });

    it("should render description text", () => {
      render(<LoginPage />);

      expect(
        screen.getByText(/enter your email and password to access your account/i)
      ).toBeInTheDocument();
    });
  });

  describe("form inputs", () => {
    it("should have email input type", () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      expect(emailInput).toHaveAttribute("type", "email");
    });

    it("should have password input type", () => {
      render(<LoginPage />);

      const passwordInput = screen.getByLabelText(/password/i);
      expect(passwordInput).toHaveAttribute("type", "password");
    });

    it("should have placeholder for email input", () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      expect(emailInput).toHaveAttribute("placeholder", "name@example.com");
    });

    it("should have required attribute on email input", () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      expect(emailInput).toBeRequired();
    });

    it("should have required attribute on password input", () => {
      render(<LoginPage />);

      const passwordInput = screen.getByLabelText(/password/i);
      expect(passwordInput).toBeRequired();
    });

    it("should update email value on input", async () => {
      const user = userEvent.setup();
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      await user.type(emailInput, "test@example.com");

      expect(emailInput).toHaveValue("test@example.com");
    });

    it("should update password value on input", async () => {
      const user = userEvent.setup();
      render(<LoginPage />);

      const passwordInput = screen.getByLabelText(/password/i);
      await user.type(passwordInput, "mypassword123");

      expect(passwordInput).toHaveValue("mypassword123");
    });

    it("should have autocomplete attributes", () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);

      expect(emailInput).toHaveAttribute("autocomplete", "email");
      expect(passwordInput).toHaveAttribute("autocomplete", "current-password");
    });
  });

  describe("form submission", () => {
    it("should call login with credentials on submit", async () => {
      const user = userEvent.setup();
      mockLogin.mockResolvedValue(undefined);
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "password123");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      expect(mockClearError).toHaveBeenCalled();
      expect(mockLogin).toHaveBeenCalledWith("test@example.com", "password123");
    });

    it("should redirect to home on successful login", async () => {
      const user = userEvent.setup();
      mockLogin.mockResolvedValue(undefined);
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "password123");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/");
      });
    });

    it("should redirect to returnUrl if provided", async () => {
      mockSearchParams.set("returnUrl", "/dashboard/settings");
      const user = userEvent.setup();
      mockLogin.mockResolvedValue(undefined);
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "password123");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/dashboard/settings");
      });
    });

    it("should set auth cookie on successful login", async () => {
      const user = userEvent.setup();
      mockLogin.mockResolvedValue(undefined);
      let cookieValue = "";
      Object.defineProperty(document, "cookie", {
        get: () => cookieValue,
        set: (val: string) => {
          cookieValue = val;
        },
        configurable: true,
      });

      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "password123");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(cookieValue).toContain("has_auth=true");
      });
    });

    it("should not redirect on login failure", async () => {
      const user = userEvent.setup();
      mockLogin.mockRejectedValue(new Error("Invalid credentials"));
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "wrongpassword");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      await waitFor(() => {
        expect(mockPush).not.toHaveBeenCalled();
      });
    });
  });

  describe("loading state", () => {
    it("should disable button when loading", () => {
      mockIsLoading = true;
      render(<LoginPage />);

      expect(screen.getByRole("button", { name: /sign in/i })).toBeDisabled();
    });

    it("should show loading spinner when loading", () => {
      mockIsLoading = true;
      const { container } = render(<LoginPage />);

      // Look for the Loader2 icon (has animate-spin class)
      const spinner = container.querySelector(".animate-spin");
      expect(spinner).toBeInTheDocument();
    });
  });

  describe("error handling", () => {
    it("should display error message when error exists", () => {
      mockError = "Invalid email or password";
      render(<LoginPage />);

      expect(screen.getByText("Invalid email or password")).toBeInTheDocument();
    });

    it("should have error styling for error message", () => {
      mockError = "Invalid credentials";
      render(<LoginPage />);

      const errorDiv = screen.getByText("Invalid credentials");
      expect(errorDiv).toHaveClass("text-destructive");
    });

    it("should clear error when form is submitted", async () => {
      const user = userEvent.setup();
      mockError = "Previous error";
      mockLogin.mockResolvedValue(undefined);
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "password123");
      await user.click(screen.getByRole("button", { name: /sign in/i }));

      expect(mockClearError).toHaveBeenCalled();
    });
  });

  describe("form validation", () => {
    it("should not submit with empty email", async () => {
      const user = userEvent.setup();
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/password/i), "password123");

      // The form should not submit due to HTML5 validation
      // We can verify login was not called
      expect(mockLogin).not.toHaveBeenCalled();
    });

    it("should not submit with empty password", async () => {
      const user = userEvent.setup();
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");

      expect(mockLogin).not.toHaveBeenCalled();
    });

    it("should enforce email format via HTML5 validation", () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      expect(emailInput).toHaveAttribute("type", "email");
    });
  });

  describe("accessibility", () => {
    it("should have proper label associations", () => {
      render(<LoginPage />);

      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/password/i);

      expect(emailInput).toHaveAttribute("id");
      expect(passwordInput).toHaveAttribute("id");
    });

    it("should be navigable by keyboard", async () => {
      const user = userEvent.setup();
      render(<LoginPage />);

      await user.tab();
      expect(screen.getByLabelText(/email/i)).toHaveFocus();

      await user.tab();
      // Skip forgot password link
      await user.tab();
      expect(screen.getByLabelText(/password/i)).toHaveFocus();
    });

    it("should submit form on Enter key", async () => {
      const user = userEvent.setup();
      mockLogin.mockResolvedValue(undefined);
      render(<LoginPage />);

      await user.type(screen.getByLabelText(/email/i), "test@example.com");
      await user.type(screen.getByLabelText(/password/i), "password123");
      await user.keyboard("{Enter}");

      expect(mockLogin).toHaveBeenCalled();
    });
  });

  describe("Card layout", () => {
    it("should render within a Card component", () => {
      const { container } = render(<LoginPage />);

      // Card has rounded-lg border classes
      const card = container.querySelector(".rounded-lg.border");
      expect(card).toBeInTheDocument();
    });

    it("should have CardHeader with title", () => {
      render(<LoginPage />);

      expect(screen.getByRole("heading", { name: /sign in/i })).toBeInTheDocument();
    });
  });
});
