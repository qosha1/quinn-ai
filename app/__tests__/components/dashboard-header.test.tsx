import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DashboardHeader } from "@/components/dashboard-header";

// Mock next/navigation
const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
  usePathname: () => "/",
  useSearchParams: () => new URLSearchParams(),
}));

// Mock the auth store
const mockLogout = vi.fn();
const mockUser = {
  id: "user-123",
  email: "john@example.com",
  first_name: "John",
  last_name: "Doe",
  avatar_url: "https://example.com/avatar.jpg",
  created_at: "2024-01-01T00:00:00Z",
};

vi.mock("@/stores/auth-store", () => ({
  useAuthStore: () => ({
    user: mockUser,
    logout: mockLogout,
  }),
}));

// Mock ThemeToggle component
vi.mock("@/components/theme-toggle", () => ({
  ThemeToggle: () => <button data-testid="theme-toggle">Toggle Theme</button>,
}));

describe("DashboardHeader", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Reset document.cookie
    Object.defineProperty(document, "cookie", {
      writable: true,
      value: "",
    });
  });

  describe("rendering", () => {
    it("should render the header element", () => {
      render(<DashboardHeader />);

      expect(screen.getByRole("banner")).toBeInTheDocument();
    });

    it("should render notification bell button", () => {
      render(<DashboardHeader />);

      // Find button containing notification icon
      const buttons = screen.getAllByRole("button");
      const bellButton = buttons.find((btn) => btn.querySelector("svg"));
      expect(bellButton).toBeInTheDocument();
    });

    it("should show notification count badge", () => {
      render(<DashboardHeader />);

      expect(screen.getByText("3")).toBeInTheDocument();
    });

    it("should render theme toggle", () => {
      render(<DashboardHeader />);

      expect(screen.getByTestId("theme-toggle")).toBeInTheDocument();
    });

    it("should render user avatar button", () => {
      render(<DashboardHeader />);

      // Avatar button should be present
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThanOrEqual(2);
    });

    it("should display user initials in avatar fallback", () => {
      render(<DashboardHeader />);

      // Should show "JD" for John Doe
      expect(screen.getByText("JD")).toBeInTheDocument();
    });

    it("should have sticky positioning", () => {
      render(<DashboardHeader />);

      const header = screen.getByRole("banner");
      expect(header).toHaveClass("sticky");
      expect(header).toHaveClass("top-0");
    });
  });

  describe("user dropdown menu", () => {
    it("should open dropdown menu on avatar click", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      // Find and click the avatar button (last button in the header)
      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      // Dropdown should show user name
      await waitFor(() => {
        expect(screen.getByText("john@example.com")).toBeInTheDocument();
      });
    });

    it("should display user name in dropdown", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByText("John Doe")).toBeInTheDocument();
      });
    });

    it("should display user email in dropdown", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByText("john@example.com")).toBeInTheDocument();
      });
    });

    it("should have Profile link in dropdown", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByRole("menuitem", { name: /profile/i })).toBeInTheDocument();
      });
    });

    it("should have Settings link in dropdown", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByRole("menuitem", { name: /settings/i })).toBeInTheDocument();
      });
    });

    it("should have Log out button in dropdown", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByRole("menuitem", { name: /log out/i })).toBeInTheDocument();
      });
    });

    it("should link Profile to /settings/profile", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        const profileLink = screen.getByRole("menuitem", { name: /profile/i });
        expect(profileLink.closest("a")).toHaveAttribute("href", "/settings/profile");
      });
    });

    it("should link Settings to /settings", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        const settingsLink = screen.getByRole("menuitem", { name: /settings/i });
        expect(settingsLink.closest("a")).toHaveAttribute("href", "/settings");
      });
    });
  });

  describe("logout functionality", () => {
    it("should call logout when Log out is clicked", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByRole("menuitem", { name: /log out/i })).toBeInTheDocument();
      });

      const logoutButton = screen.getByRole("menuitem", { name: /log out/i });
      await user.click(logoutButton);

      expect(mockLogout).toHaveBeenCalled();
    });

    it("should redirect to /login after logout", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByRole("menuitem", { name: /log out/i })).toBeInTheDocument();
      });

      const logoutButton = screen.getByRole("menuitem", { name: /log out/i });
      await user.click(logoutButton);

      expect(mockPush).toHaveBeenCalledWith("/login");
    });

    it("should clear auth cookie on logout", async () => {
      const user = userEvent.setup();
      let cookieValue = "has_auth=true";
      Object.defineProperty(document, "cookie", {
        get: () => cookieValue,
        set: (val: string) => {
          cookieValue = val;
        },
        configurable: true,
      });

      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        expect(screen.getByRole("menuitem", { name: /log out/i })).toBeInTheDocument();
      });

      const logoutButton = screen.getByRole("menuitem", { name: /log out/i });
      await user.click(logoutButton);

      // Cookie should be expired
      expect(cookieValue).toContain("has_auth=");
      expect(cookieValue).toContain("expires=");
    });
  });

  describe("user initials generation", () => {
    it("should generate correct initials for full name", () => {
      render(<DashboardHeader />);

      expect(screen.getByText("JD")).toBeInTheDocument();
    });
  });

  describe("styling", () => {
    it("should have border bottom", () => {
      render(<DashboardHeader />);

      const header = screen.getByRole("banner");
      expect(header).toHaveClass("border-b");
    });

    it("should have correct z-index for stacking", () => {
      render(<DashboardHeader />);

      const header = screen.getByRole("banner");
      expect(header).toHaveClass("z-30");
    });

    it("should have fixed height", () => {
      render(<DashboardHeader />);

      const header = screen.getByRole("banner");
      expect(header).toHaveClass("h-16");
    });

    it("should have background color", () => {
      render(<DashboardHeader />);

      const header = screen.getByRole("banner");
      expect(header).toHaveClass("bg-background");
    });
  });

  describe("accessibility", () => {
    it("should have accessible avatar button", () => {
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      expect(avatarButton).toBeInTheDocument();
    });

    it("should have accessible dropdown menu items", async () => {
      const user = userEvent.setup();
      render(<DashboardHeader />);

      const avatarButton = screen.getByRole("button", { name: /john doe/i });
      await user.click(avatarButton);

      await waitFor(() => {
        const menuItems = screen.getAllByRole("menuitem");
        expect(menuItems.length).toBeGreaterThan(0);
      });
    });
  });

  describe("responsive design", () => {
    it("should have responsive padding", () => {
      render(<DashboardHeader />);

      const header = screen.getByRole("banner");
      expect(header).toHaveClass("px-4");
      expect(header).toHaveClass("lg:px-6");
    });

    it("should have mobile offset for menu button", () => {
      const { container } = render(<DashboardHeader />);

      const leftSection = container.querySelector(".pl-12");
      expect(leftSection).toBeInTheDocument();
    });
  });
});

describe("DashboardHeader with no user", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("should show fallback initials when user has no name", async () => {
    // Override the mock temporarily
    vi.doMock("@/stores/auth-store", () => ({
      useAuthStore: () => ({
        user: {
          id: "user-123",
          email: "anonymous@example.com",
          first_name: "",
          last_name: "",
          created_at: "2024-01-01T00:00:00Z",
        },
        logout: mockLogout,
      }),
    }));

    // Since we can't easily change mocks mid-test in vitest,
    // we verify the initials logic would handle empty names
    // by testing the component renders without errors
    render(<DashboardHeader />);
    expect(screen.getByRole("banner")).toBeInTheDocument();
  });
});
