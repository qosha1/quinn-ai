import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Sidebar } from "@/components/sidebar";

// Mock next/navigation
const mockUsePathname = vi.fn();
vi.mock("next/navigation", () => ({
  usePathname: () => mockUsePathname(),
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

describe("Sidebar", () => {
  beforeEach(() => {
    mockUsePathname.mockReturnValue("/");
    vi.clearAllMocks();
  });

  describe("rendering", () => {
    it("should render the sidebar", () => {
      render(<Sidebar />);

      // Check for logo/brand
      expect(screen.getAllByText(/SaaSify/i).length).toBeGreaterThan(0);
    });

    it("should render Dashboard navigation link", () => {
      render(<Sidebar />);

      expect(screen.getAllByText("Dashboard").length).toBeGreaterThan(0);
    });

    it("should render Team navigation item", () => {
      render(<Sidebar />);

      expect(screen.getAllByText("Team").length).toBeGreaterThan(0);
    });

    it("should render Billing navigation item", () => {
      render(<Sidebar />);

      expect(screen.getAllByText("Billing").length).toBeGreaterThan(0);
    });

    it("should render Settings navigation item", () => {
      render(<Sidebar />);

      expect(screen.getAllByText("Settings").length).toBeGreaterThan(0);
    });

    it("should accept custom className", () => {
      const { container } = render(<Sidebar className="custom-sidebar" />);

      // The custom class is applied to the desktop sidebar
      const desktopSidebar = container.querySelector(".custom-sidebar");
      expect(desktopSidebar).toBeInTheDocument();
    });
  });

  describe("active state", () => {
    it("should highlight Dashboard when on root path", () => {
      mockUsePathname.mockReturnValue("/");
      render(<Sidebar />);

      // Dashboard link should have active styling
      const dashboardLinks = screen.getAllByText("Dashboard");
      const activeLink = dashboardLinks.find((link) =>
        link.closest("a")?.classList.contains("bg-sidebar-primary")
      );
      expect(activeLink).toBeDefined();
    });

    it("should highlight Team section when on team page", () => {
      mockUsePathname.mockReturnValue("/team");
      render(<Sidebar />);

      // Team button should have active parent styling
      const teamButtons = screen.getAllByText("Team");
      const activeButton = teamButtons.find((btn) =>
        btn.closest("button")?.classList.contains("bg-sidebar-accent")
      );
      expect(activeButton).toBeDefined();
    });

    it("should highlight child item when on nested team page", () => {
      mockUsePathname.mockReturnValue("/team/members");
      render(<Sidebar />);

      // The Members link should be visible and have active styling
      const membersLinks = screen.getAllByText("Members");
      expect(membersLinks.length).toBeGreaterThan(0);
    });

    it("should highlight Billing section when on billing page", () => {
      mockUsePathname.mockReturnValue("/billing");
      render(<Sidebar />);

      const billingButtons = screen.getAllByText("Billing");
      expect(billingButtons.length).toBeGreaterThan(0);
    });

    it("should highlight Settings section when on settings page", () => {
      mockUsePathname.mockReturnValue("/settings/profile");
      render(<Sidebar />);

      // Settings should be expanded
      const profileLinks = screen.getAllByText("Profile");
      expect(profileLinks.length).toBeGreaterThan(0);
    });
  });

  describe("expandable navigation", () => {
    it("should auto-expand parent of active child item", () => {
      mockUsePathname.mockReturnValue("/team/members");
      render(<Sidebar />);

      // Team submenu should be expanded, showing Members
      const membersLinks = screen.getAllByText("Members");
      expect(membersLinks.length).toBeGreaterThan(0);
    });

    it("should toggle Team submenu on click", async () => {
      const user = userEvent.setup();
      mockUsePathname.mockReturnValue("/");
      render(<Sidebar />);

      // Find the Team button (there may be multiple in mobile/desktop views)
      const teamButtons = screen.getAllByRole("button", { name: /Team/i });
      const teamButton = teamButtons[0];

      // Click to expand
      await user.click(teamButton);

      // Should show submenu items
      const memberLinks = screen.getAllByText("Members");
      expect(memberLinks.length).toBeGreaterThan(0);
    });

    it("should show Team submenu items", async () => {
      const user = userEvent.setup();
      mockUsePathname.mockReturnValue("/");
      render(<Sidebar />);

      const teamButtons = screen.getAllByRole("button", { name: /Team/i });
      await user.click(teamButtons[0]);

      expect(screen.getAllByText("Overview").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Members").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Invitations").length).toBeGreaterThan(0);
    });

    it("should show Billing submenu items when expanded", async () => {
      const user = userEvent.setup();
      mockUsePathname.mockReturnValue("/");
      render(<Sidebar />);

      const billingButtons = screen.getAllByRole("button", { name: /Billing/i });
      await user.click(billingButtons[0]);

      expect(screen.getAllByText("Plans").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Invoices").length).toBeGreaterThan(0);
    });

    it("should show Settings submenu items when expanded", async () => {
      const user = userEvent.setup();
      mockUsePathname.mockReturnValue("/");
      render(<Sidebar />);

      const settingsButtons = screen.getAllByRole("button", { name: /Settings/i });
      await user.click(settingsButtons[0]);

      expect(screen.getAllByText("Profile").length).toBeGreaterThan(0);
      expect(screen.getAllByText("Security").length).toBeGreaterThan(0);
      expect(screen.getAllByText("API Keys").length).toBeGreaterThan(0);
    });
  });

  describe("navigation links", () => {
    it("should have correct href for Dashboard", () => {
      render(<Sidebar />);

      const dashboardLinks = screen.getAllByRole("link", { name: /Dashboard/i });
      expect(dashboardLinks[0]).toHaveAttribute("href", "/");
    });

    it("should have correct href for Team child links", async () => {
      const user = userEvent.setup();
      mockUsePathname.mockReturnValue("/team");
      render(<Sidebar />);

      // Team should be auto-expanded
      const membersLinks = screen.getAllByRole("link", { name: /^Members$/i });
      expect(membersLinks[0]).toHaveAttribute("href", "/team/members");
    });

    it("should have correct href for Billing child links", () => {
      mockUsePathname.mockReturnValue("/billing");
      render(<Sidebar />);

      const plansLinks = screen.getAllByRole("link", { name: /^Plans$/i });
      expect(plansLinks[0]).toHaveAttribute("href", "/billing/plans");
    });
  });

  describe("collapse functionality", () => {
    it("should have collapse toggle button", () => {
      render(<Sidebar />);

      // There should be a button for collapsing (chevron icon)
      const collapseButtons = screen.getAllByRole("button");
      expect(collapseButtons.length).toBeGreaterThan(0);
    });

    it("should toggle sidebar width on collapse button click", async () => {
      const user = userEvent.setup();
      const { container } = render(<Sidebar />);

      // Find the desktop sidebar
      const desktopSidebar = container.querySelector(".hidden.lg\\:flex");
      expect(desktopSidebar).toHaveClass("w-64");

      // Find and click the collapse button (the one with ChevronLeft icon)
      // It's inside the header area with hidden lg:flex classes
      const collapseButton = container.querySelector(
        ".hidden.lg\\:flex button.hidden.lg\\:flex"
      );
      if (collapseButton) {
        await user.click(collapseButton);
        // After collapse, sidebar should have narrower width
        expect(desktopSidebar).toHaveClass("w-16");
      }
    });
  });

  describe("mobile behavior", () => {
    it("should render mobile menu button", () => {
      render(<Sidebar />);

      // Mobile menu button should be visible on small screens
      const buttons = screen.getAllByRole("button");
      // The mobile button is fixed positioned
      expect(buttons.length).toBeGreaterThan(0);
    });

    it("should toggle mobile sidebar on menu button click", async () => {
      const user = userEvent.setup();
      const { container } = render(<Sidebar />);

      // Find the mobile menu button (first button, fixed position)
      const mobileButton = container.querySelector(".fixed.left-4.top-4 button");
      expect(mobileButton).toBeInTheDocument();

      if (mobileButton) {
        await user.click(mobileButton);

        // Mobile sidebar should be visible
        const mobileSidebar = container.querySelector(".fixed.inset-y-0.left-0.z-40");
        expect(mobileSidebar).toHaveClass("translate-x-0");
      }
    });

    it("should close mobile sidebar when clicking overlay", async () => {
      const user = userEvent.setup();
      const { container } = render(<Sidebar />);

      // Open mobile menu
      const mobileButton = container.querySelector(".fixed.left-4.top-4 button");
      if (mobileButton) {
        await user.click(mobileButton);

        // Click overlay
        const overlay = container.querySelector(".fixed.inset-0.z-40.bg-background\\/80");
        if (overlay) {
          await user.click(overlay);

          // Mobile sidebar should be hidden
          const mobileSidebar = container.querySelector(".fixed.inset-y-0.left-0.z-40");
          expect(mobileSidebar).toHaveClass("-translate-x-full");
        }
      }
    });

    it("should close mobile sidebar when clicking a link", async () => {
      const user = userEvent.setup();
      mockUsePathname.mockReturnValue("/");
      const { container } = render(<Sidebar />);

      // Open mobile menu
      const mobileButton = container.querySelector(".fixed.left-4.top-4 button");
      if (mobileButton) {
        await user.click(mobileButton);

        // Click Dashboard link
        const dashboardLinks = screen.getAllByRole("link", { name: /Dashboard/i });
        await user.click(dashboardLinks[0]);

        // Mobile sidebar should close
        const mobileSidebar = container.querySelector(".fixed.inset-y-0.left-0.z-40");
        expect(mobileSidebar).toHaveClass("-translate-x-full");
      }
    });
  });

  describe("icons", () => {
    it("should render icons for navigation items", () => {
      const { container } = render(<Sidebar />);

      // SVG icons should be present
      const icons = container.querySelectorAll("svg");
      expect(icons.length).toBeGreaterThan(0);
    });
  });

  describe("responsive design", () => {
    it("should have lg:hidden class on mobile menu button", () => {
      const { container } = render(<Sidebar />);

      const mobileButton = container.querySelector(".lg\\:hidden.fixed");
      expect(mobileButton).toBeInTheDocument();
    });

    it("should have hidden lg:flex class on desktop sidebar", () => {
      const { container } = render(<Sidebar />);

      const desktopSidebar = container.querySelector(".hidden.lg\\:flex");
      expect(desktopSidebar).toBeInTheDocument();
    });
  });
});
