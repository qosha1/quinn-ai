import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RegisterPage from "@/app/(auth)/register/page";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// Mock the API
const mockRegister = vi.fn();
vi.mock("@/lib/api", () => ({
  authApi: {
    register: (...args: unknown[]) => mockRegister(...args),
  },
}));

describe("RegisterPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("rendering", () => {
    it("should render registration form", () => {
      render(<RegisterPage />);

      expect(screen.getByRole("heading", { name: /create an account/i })).toBeInTheDocument();
    });

    it("should render first name input", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/first name/i)).toBeInTheDocument();
    });

    it("should render last name input", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/last name/i)).toBeInTheDocument();
    });

    it("should render email input", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    });

    it("should render password input", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/^password$/i)).toBeInTheDocument();
    });

    it("should render confirm password input", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/confirm password/i)).toBeInTheDocument();
    });

    it("should render create account button", () => {
      render(<RegisterPage />);

      expect(screen.getByRole("button", { name: /create account/i })).toBeInTheDocument();
    });

    it("should render sign in link", () => {
      render(<RegisterPage />);

      expect(screen.getByRole("link", { name: /sign in/i })).toBeInTheDocument();
    });

    it("should link sign in to /login", () => {
      render(<RegisterPage />);

      const link = screen.getByRole("link", { name: /sign in/i });
      expect(link).toHaveAttribute("href", "/login");
    });

    it("should render description text", () => {
      render(<RegisterPage />);

      expect(screen.getByText(/enter your information to get started/i)).toBeInTheDocument();
    });
  });

  describe("form inputs", () => {
    it("should have correct input types", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/email/i)).toHaveAttribute("type", "email");
      expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("type", "password");
      expect(screen.getByLabelText(/confirm password/i)).toHaveAttribute("type", "password");
    });

    it("should have required attributes on all fields", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/first name/i)).toBeRequired();
      expect(screen.getByLabelText(/last name/i)).toBeRequired();
      expect(screen.getByLabelText(/email/i)).toBeRequired();
      expect(screen.getByLabelText(/^password$/i)).toBeRequired();
      expect(screen.getByLabelText(/confirm password/i)).toBeRequired();
    });

    it("should have placeholder text", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/first name/i)).toHaveAttribute("placeholder", "John");
      expect(screen.getByLabelText(/last name/i)).toHaveAttribute("placeholder", "Doe");
      expect(screen.getByLabelText(/email/i)).toHaveAttribute("placeholder", "name@example.com");
    });

    it("should have autocomplete attributes", () => {
      render(<RegisterPage />);

      expect(screen.getByLabelText(/first name/i)).toHaveAttribute("autocomplete", "given-name");
      expect(screen.getByLabelText(/last name/i)).toHaveAttribute("autocomplete", "family-name");
      expect(screen.getByLabelText(/email/i)).toHaveAttribute("autocomplete", "email");
      expect(screen.getByLabelText(/^password$/i)).toHaveAttribute("autocomplete", "new-password");
      expect(screen.getByLabelText(/confirm password/i)).toHaveAttribute(
        "autocomplete",
        "new-password"
      );
    });

    it("should update form values on input", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");

      expect(screen.getByLabelText(/first name/i)).toHaveValue("John");
      expect(screen.getByLabelText(/last name/i)).toHaveValue("Doe");
      expect(screen.getByLabelText(/email/i)).toHaveValue("john@example.com");
      expect(screen.getByLabelText(/^password$/i)).toHaveValue("password123");
      expect(screen.getByLabelText(/confirm password/i)).toHaveValue("password123");
    });
  });

  describe("form submission", () => {
    it("should call register API with form data on submit", async () => {
      const user = userEvent.setup();
      mockRegister.mockResolvedValue({ data: { id: "user-123" } });
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalledWith({
          email: "john@example.com",
          password: "password123",
          first_name: "John",
          last_name: "Doe",
        });
      });
    });

    it("should redirect to login with registered param on success", async () => {
      const user = userEvent.setup();
      mockRegister.mockResolvedValue({ data: { id: "user-123" } });
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(mockPush).toHaveBeenCalledWith("/login?registered=true");
      });
    });
  });

  describe("validation", () => {
    it("should show error when passwords do not match", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "differentpassword");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
      });
    });

    it("should not call register when passwords do not match", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "differentpassword");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(mockRegister).not.toHaveBeenCalled();
      });
    });

    it("should show error when password is too short", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "short");
      await user.type(screen.getByLabelText(/confirm password/i), "short");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/password must be at least 8 characters/i)).toBeInTheDocument();
      });
    });

    it("should not call register when password is too short", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "short");
      await user.type(screen.getByLabelText(/confirm password/i), "short");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(mockRegister).not.toHaveBeenCalled();
      });
    });

    it("should accept password with exactly 8 characters", async () => {
      const user = userEvent.setup();
      mockRegister.mockResolvedValue({ data: { id: "user-123" } });
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "exactly8");
      await user.type(screen.getByLabelText(/confirm password/i), "exactly8");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalled();
      });
    });
  });

  describe("error handling", () => {
    it("should display API error message", async () => {
      const user = userEvent.setup();
      mockRegister.mockRejectedValue(new Error("Email already exists"));
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText("Email already exists")).toBeInTheDocument();
      });
    });

    it("should display default error message for non-Error exceptions", async () => {
      const user = userEvent.setup();
      mockRegister.mockRejectedValue("Unknown error");
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText("Failed to create account")).toBeInTheDocument();
      });
    });

    it("should have error styling for error messages", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "mismatch");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        const errorDiv = screen.getByText(/passwords do not match/i);
        expect(errorDiv).toHaveClass("text-destructive");
      });
    });

    it("should clear error on new submission attempt", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      // First submission with mismatched passwords
      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "mismatch");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByText(/passwords do not match/i)).toBeInTheDocument();
      });

      // Clear and retry with matching passwords
      await user.clear(screen.getByLabelText(/confirm password/i));
      await user.type(screen.getByLabelText(/confirm password/i), "password123");

      mockRegister.mockResolvedValue({ data: { id: "user-123" } });
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.queryByText(/passwords do not match/i)).not.toBeInTheDocument();
      });
    });
  });

  describe("loading state", () => {
    it("should disable button during submission", async () => {
      const user = userEvent.setup();
      // Create a promise that doesn't resolve immediately
      let resolveRegister: (value: unknown) => void;
      const registerPromise = new Promise((resolve) => {
        resolveRegister = resolve;
      });
      mockRegister.mockReturnValue(registerPromise);
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      // Button should be disabled while loading
      expect(screen.getByRole("button", { name: /create account/i })).toBeDisabled();

      // Resolve the promise
      resolveRegister!({ data: { id: "user-123" } });
    });

    it("should show loading spinner during submission", async () => {
      const user = userEvent.setup();
      let resolveRegister: (value: unknown) => void;
      const registerPromise = new Promise((resolve) => {
        resolveRegister = resolve;
      });
      mockRegister.mockReturnValue(registerPromise);
      const { container } = render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      // Should show spinner
      const spinner = container.querySelector(".animate-spin");
      expect(spinner).toBeInTheDocument();

      // Resolve the promise
      resolveRegister!({ data: { id: "user-123" } });
    });

    it("should re-enable button after submission completes", async () => {
      const user = userEvent.setup();
      mockRegister.mockRejectedValue(new Error("API error"));
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.click(screen.getByRole("button", { name: /create account/i }));

      await waitFor(() => {
        expect(screen.getByRole("button", { name: /create account/i })).not.toBeDisabled();
      });
    });
  });

  describe("accessibility", () => {
    it("should have proper label associations", () => {
      render(<RegisterPage />);

      const firstNameInput = screen.getByLabelText(/first name/i);
      const lastNameInput = screen.getByLabelText(/last name/i);
      const emailInput = screen.getByLabelText(/email/i);
      const passwordInput = screen.getByLabelText(/^password$/i);
      const confirmPasswordInput = screen.getByLabelText(/confirm password/i);

      expect(firstNameInput).toHaveAttribute("id");
      expect(lastNameInput).toHaveAttribute("id");
      expect(emailInput).toHaveAttribute("id");
      expect(passwordInput).toHaveAttribute("id");
      expect(confirmPasswordInput).toHaveAttribute("id");
    });

    it("should be navigable by keyboard", async () => {
      const user = userEvent.setup();
      render(<RegisterPage />);

      await user.tab();
      expect(screen.getByLabelText(/first name/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/last name/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/email/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/^password$/i)).toHaveFocus();

      await user.tab();
      expect(screen.getByLabelText(/confirm password/i)).toHaveFocus();
    });

    it("should submit form on Enter key", async () => {
      const user = userEvent.setup();
      mockRegister.mockResolvedValue({ data: { id: "user-123" } });
      render(<RegisterPage />);

      await user.type(screen.getByLabelText(/first name/i), "John");
      await user.type(screen.getByLabelText(/last name/i), "Doe");
      await user.type(screen.getByLabelText(/email/i), "john@example.com");
      await user.type(screen.getByLabelText(/^password$/i), "password123");
      await user.type(screen.getByLabelText(/confirm password/i), "password123");
      await user.keyboard("{Enter}");

      await waitFor(() => {
        expect(mockRegister).toHaveBeenCalled();
      });
    });
  });

  describe("layout", () => {
    it("should render name fields in a grid layout", () => {
      const { container } = render(<RegisterPage />);

      const grid = container.querySelector(".grid.grid-cols-2");
      expect(grid).toBeInTheDocument();
    });

    it("should render within a Card component", () => {
      const { container } = render(<RegisterPage />);

      const card = container.querySelector(".rounded-lg.border");
      expect(card).toBeInTheDocument();
    });
  });
});
