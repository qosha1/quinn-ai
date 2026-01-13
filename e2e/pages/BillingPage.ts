import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the billing pages.
 */
export class BillingPage extends BasePage {
  // Main billing page selectors
  readonly pageTitle = 'h1:has-text("Billing")';
  readonly manageBillingButton = 'button:has-text("Manage Billing")';
  readonly currentPlanSection = 'text=/Current Plan/i';
  readonly usageSection = 'text=/Usage/i';

  // Plan details
  readonly planName = '.text-2xl.font-bold';
  readonly planPrice = 'text=/\\$/';
  readonly changePlanButton = 'a:has-text("Change Plan"), button:has-text("Change Plan")';
  readonly currentPeriod = 'text=/Current period/i';
  readonly cancelNotice = 'text=/will be canceled/i';

  // Usage stats
  readonly membersUsage = 'text=/Team Members/i';
  readonly storageUsage = 'text=/Storage/i';
  readonly apiCallsUsage = 'text=/API Calls/i';

  // Quick links
  readonly plansLink = 'a[href="/billing/plans"]';
  readonly invoicesLink = 'a[href="/billing/invoices"]';
  readonly paymentMethodLink = 'text=/Payment Method/i';

  // Plans page
  readonly plansTitle = 'h1:has-text("Plans")';
  readonly freePlanCard = 'text=/Free/i';
  readonly proPlanCard = 'text=/Pro/i';
  readonly enterprisePlanCard = 'text=/Enterprise/i';
  readonly selectPlanButton = 'button:has-text("Select"), button:has-text("Upgrade")';
  readonly currentPlanBadge = 'text=/Current Plan/i';

  // Invoices page
  readonly invoicesTitle = 'h1:has-text("Invoices")';
  readonly invoicesTable = 'table';
  readonly invoiceRow = 'tbody tr';
  readonly downloadInvoiceButton = 'a:has-text("Download"), button:has-text("Download")';

  // Status badges
  readonly activeStatus = 'text=/Active/i';
  readonly trialStatus = 'text=/Trial/i';
  readonly pastDueStatus = 'text=/Past Due/i';
  readonly canceledStatus = 'text=/Canceled/i';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(`${TEST_URLS.app}/billing`);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.pageTitle);
  }

  /**
   * Navigate to Plans page.
   */
  async goToPlans(): Promise<void> {
    await this.page.click(this.plansLink);
    await this.page.waitForURL('**/billing/plans');
  }

  /**
   * Navigate to Invoices page.
   */
  async goToInvoices(): Promise<void> {
    await this.page.click(this.invoicesLink);
    await this.page.waitForURL('**/billing/invoices');
  }

  /**
   * Click Manage Billing to open Stripe portal.
   */
  async clickManageBilling(): Promise<void> {
    await this.page.click(this.manageBillingButton);
  }

  /**
   * Get current plan name.
   */
  async getCurrentPlanName(): Promise<string | null> {
    const planElement = this.page.locator(this.currentPlanSection).locator('..').locator(this.planName);
    return planElement.textContent();
  }

  /**
   * Get subscription status.
   */
  async getSubscriptionStatus(): Promise<string | null> {
    const badge = this.page.locator('.badge, [class*="badge"]').first();
    return badge.textContent();
  }

  /**
   * Click Change Plan button.
   */
  async clickChangePlan(): Promise<void> {
    await this.page.click(this.changePlanButton);
    await this.page.waitForURL('**/billing/plans');
  }

  /**
   * Select a plan by name.
   */
  async selectPlan(planName: string): Promise<void> {
    const planCard = this.page.locator(`text="${planName}"`).locator('..').locator('..');
    await planCard.locator(this.selectPlanButton).click();
  }

  /**
   * Get usage percentage for a metric.
   */
  async getUsagePercentage(metric: 'members' | 'storage' | 'apiCalls'): Promise<number> {
    let selector: string;
    switch (metric) {
      case 'members':
        selector = this.membersUsage;
        break;
      case 'storage':
        selector = this.storageUsage;
        break;
      case 'apiCalls':
        selector = this.apiCallsUsage;
        break;
    }
    const usageText = await this.page.locator(selector).locator('..').locator('text=/\\d+.*\\/.*\\d+/').textContent();
    // Parse "X / Y" format
    if (usageText) {
      const [used, limit] = usageText.split('/').map((s) => parseFloat(s.replace(/[^\d.]/g, '')));
      return Math.round((used / limit) * 100);
    }
    return 0;
  }

  /**
   * Get invoice count.
   */
  async getInvoiceCount(): Promise<number> {
    const rows = this.page.locator(this.invoiceRow);
    return rows.count();
  }

  /**
   * Download invoice by index.
   */
  async downloadInvoice(index: number): Promise<void> {
    const row = this.page.locator(this.invoiceRow).nth(index);
    await row.locator(this.downloadInvoiceButton).click();
  }

  /**
   * Check if subscription is active.
   */
  async isSubscriptionActive(): Promise<boolean> {
    return this.isVisible(this.activeStatus);
  }

  /**
   * Check if subscription is in trial.
   */
  async isSubscriptionTrial(): Promise<boolean> {
    return this.isVisible(this.trialStatus);
  }

  /**
   * Check if subscription is past due.
   */
  async isSubscriptionPastDue(): Promise<boolean> {
    return this.isVisible(this.pastDueStatus);
  }

  /**
   * Check if subscription is canceled.
   */
  async isSubscriptionCanceled(): Promise<boolean> {
    return this.isVisible(this.canceledStatus);
  }

  /**
   * Assert billing page is displayed.
   */
  async assertBillingPageVisible(): Promise<void> {
    await expect(this.page.locator(this.pageTitle)).toBeVisible();
  }

  /**
   * Assert current plan section is visible.
   */
  async assertCurrentPlanVisible(): Promise<void> {
    await expect(this.page.locator(this.currentPlanSection)).toBeVisible();
  }

  /**
   * Assert usage section is visible.
   */
  async assertUsageVisible(): Promise<void> {
    await expect(this.page.locator(this.usageSection)).toBeVisible();
  }

  /**
   * Assert plan is marked as current.
   */
  async assertPlanIsCurrent(planName: string): Promise<void> {
    const planCard = this.page.locator(`text="${planName}"`).locator('..').locator('..');
    await expect(planCard.locator(this.currentPlanBadge)).toBeVisible();
  }

  /**
   * Assert no subscription message.
   */
  async assertNoSubscription(): Promise<void> {
    await expect(this.page.locator("text=/don't have an active subscription/i")).toBeVisible();
  }

  /**
   * Assert invoices table is visible.
   */
  async assertInvoicesTableVisible(): Promise<void> {
    await expect(this.page.locator(this.invoicesTable)).toBeVisible();
  }

  /**
   * Assert no invoices message.
   */
  async assertNoInvoices(): Promise<void> {
    await expect(this.page.locator('text=/No invoices/i')).toBeVisible();
  }
}
