import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the dashboard page.
 */
export class DashboardPage extends BasePage {
  // Selectors
  readonly pageTitle = 'h1:has-text("Dashboard")';
  readonly welcomeMessage = 'text=/Welcome back/i';
  readonly statsGrid = '.grid';
  readonly totalMembersCard = 'text=/Total Members/i';
  readonly currentPlanCard = 'text=/Current Plan/i';
  readonly apiCallsCard = 'text=/API Calls/i';
  readonly storageCard = 'text=/Storage/i';
  readonly recentActivity = 'text=/Recent Activity/i';

  // Navigation
  readonly sidebar = 'nav';
  readonly dashboardLink = 'a[href="/"]';
  readonly teamLink = 'a[href="/team"]';
  readonly billingLink = 'a[href="/billing"]';
  readonly settingsLink = 'a[href="/settings"]';

  // User menu
  readonly userMenu = 'button[aria-haspopup="menu"]';
  readonly logoutButton = 'text=/Logout|Sign out/i';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(TEST_URLS.app);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.pageTitle);
  }

  /**
   * Get welcome message text.
   */
  async getWelcomeMessage(): Promise<string | null> {
    return this.getText(this.welcomeMessage);
  }

  /**
   * Check if dashboard stats are visible.
   */
  async hasStats(): Promise<boolean> {
    const membersVisible = await this.isVisible(this.totalMembersCard);
    const planVisible = await this.isVisible(this.currentPlanCard);
    return membersVisible && planVisible;
  }

  /**
   * Navigate to Team page.
   */
  async navigateToTeam(): Promise<void> {
    await this.page.click(this.teamLink);
    await this.page.waitForURL('**/team');
  }

  /**
   * Navigate to Billing page.
   */
  async navigateToBilling(): Promise<void> {
    await this.page.click(this.billingLink);
    await this.page.waitForURL('**/billing');
  }

  /**
   * Navigate to Settings page.
   */
  async navigateToSettings(): Promise<void> {
    await this.page.click(this.settingsLink);
    await this.page.waitForURL('**/settings');
  }

  /**
   * Open user menu.
   */
  async openUserMenu(): Promise<void> {
    await this.page.click(this.userMenu);
  }

  /**
   * Logout from the application.
   */
  async logout(): Promise<void> {
    await this.openUserMenu();
    await this.page.click(this.logoutButton);
    await this.page.waitForURL('**/login');
  }

  /**
   * Assert dashboard is displayed.
   */
  async assertDashboardVisible(): Promise<void> {
    await expect(this.page.locator(this.pageTitle)).toBeVisible();
  }

  /**
   * Assert welcome message contains user name.
   */
  async assertWelcomeContains(name: string): Promise<void> {
    await expect(this.page.locator(this.welcomeMessage)).toContainText(name);
  }

  /**
   * Assert all stat cards are visible.
   */
  async assertStatsVisible(): Promise<void> {
    await expect(this.page.locator(this.totalMembersCard)).toBeVisible();
    await expect(this.page.locator(this.currentPlanCard)).toBeVisible();
    await expect(this.page.locator(this.apiCallsCard)).toBeVisible();
    await expect(this.page.locator(this.storageCard)).toBeVisible();
  }

  /**
   * Assert recent activity section is visible.
   */
  async assertRecentActivityVisible(): Promise<void> {
    await expect(this.page.locator(this.recentActivity)).toBeVisible();
  }

  /**
   * Assert navigation sidebar is visible.
   */
  async assertSidebarVisible(): Promise<void> {
    await expect(this.page.locator(this.sidebar)).toBeVisible();
  }

  /**
   * Get stat card value by title.
   */
  async getStatValue(statTitle: string): Promise<string | null> {
    const card = this.page.locator(`text="${statTitle}"`).locator('..');
    const value = card.locator('.text-2xl');
    return value.textContent();
  }
}
