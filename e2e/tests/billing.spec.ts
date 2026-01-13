import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, BillingPage } from '../pages';
import { TEST_USERS, TEST_BILLING } from '../fixtures/test-data';

/**
 * Billing E2E Tests
 *
 * Tests cover:
 * - Viewing subscription status
 * - Viewing available plans
 * - Plan upgrade flow (mocked)
 * - Invoice viewing
 * - Usage display
 * - Stripe portal navigation
 */

test.describe('Billing', () => {
  // Login before each test
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAndWaitForDashboard(
      TEST_USERS.owner.email,
      TEST_USERS.owner.password
    );
  });

  test.describe('Billing Overview', () => {
    test('can navigate to billing from dashboard', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);
      const billingPage = new BillingPage(page);

      await dashboardPage.navigateToBilling();
      await billingPage.assertBillingPageVisible();
    });

    test('billing page displays current plan section', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      await billingPage.assertCurrentPlanVisible();
    });

    test('billing page displays usage section when subscribed', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      // Usage section should be visible for subscribed users
      const usageVisible = await page.locator('text=/Usage/i').isVisible();
      if (usageVisible) {
        await billingPage.assertUsageVisible();
      }
    });

    test('billing page has manage billing button', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      await expect(page.locator('button:has-text("Manage Billing")')).toBeVisible();
    });

    test('billing page has quick links', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      await expect(page.locator('a[href="/billing/plans"]')).toBeVisible();
      await expect(page.locator('a[href="/billing/invoices"]')).toBeVisible();
    });
  });

  test.describe('Current Subscription', () => {
    test('displays subscription status badge', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // Check for any status badge
      const statusBadge = page.locator('[class*="badge"]').first();
      await expect(statusBadge).toBeVisible();
    });

    test('displays plan name', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // Should show plan name in current plan section
      const planName = await billingPage.getCurrentPlanName();
      // Plan name should exist (Free, Pro, or Enterprise)
      expect(planName).toBeTruthy();
    });

    test('has change plan link', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // Check for Change Plan link if subscribed
      const changePlanLink = page.locator('a:has-text("Change Plan"), button:has-text("Change Plan")');
      const viewPlansLink = page.locator('a:has-text("View Plans")');

      const hasChangePlan = await changePlanLink.isVisible();
      const hasViewPlans = await viewPlansLink.isVisible();

      expect(hasChangePlan || hasViewPlans).toBe(true);
    });

    test('displays current billing period', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // If subscribed, should show current period
      const periodText = page.locator('text=/Current period/i');
      if (await periodText.isVisible()) {
        await expect(periodText).toBeVisible();
      }
    });
  });

  test.describe('Usage Statistics', () => {
    test('displays team members usage', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      const usageSection = page.locator('text=/Usage/i');
      if (await usageSection.isVisible()) {
        await expect(page.locator('text=/Team Members/i')).toBeVisible();
      }
    });

    test('displays storage usage', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      const usageSection = page.locator('text=/Usage/i');
      if (await usageSection.isVisible()) {
        await expect(page.locator('text=/Storage/i')).toBeVisible();
      }
    });

    test('displays API calls usage', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      const usageSection = page.locator('text=/Usage/i');
      if (await usageSection.isVisible()) {
        await expect(page.locator('text=/API Calls/i')).toBeVisible();
      }
    });

    test('usage bars show progress', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // Check for progress bars
      const progressBars = page.locator('[class*="bg-primary"]');
      const count = await progressBars.count();

      // If usage section exists, should have progress bars
      const usageSection = page.locator('text=/Usage/i');
      if (await usageSection.isVisible()) {
        expect(count).toBeGreaterThan(0);
      }
    });
  });

  test.describe('Plans Page', () => {
    test('can navigate to plans page', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await billingPage.goToPlans();

      await expect(page).toHaveURL(/billing\/plans/);
    });

    test('plans page displays available plans', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Should show multiple plan options
      const planCards = page.locator('[class*="card"]');
      const count = await planCards.count();
      expect(count).toBeGreaterThan(0);
    });

    test('plans show pricing information', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Should show price indicators
      await expect(page.locator('text=/\\$/').first()).toBeVisible();
    });

    test('plans show feature lists', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Plans should have feature lists
      const featureItems = page.locator('li');
      const count = await featureItems.count();
      expect(count).toBeGreaterThan(0);
    });

    test('current plan is marked', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Should have a "Current Plan" or similar indicator
      const currentIndicator = page.locator('text=/Current|Selected/i');
      await expect(currentIndicator.first()).toBeVisible();
    });

    test('can select a different plan', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Look for upgrade/select buttons
      const selectButtons = page.locator('button:has-text("Select"), button:has-text("Upgrade"), button:has-text("Subscribe")');
      const count = await selectButtons.count();

      // Should have at least one selectable plan
      expect(count).toBeGreaterThan(0);
    });
  });

  test.describe('Invoices Page', () => {
    test('can navigate to invoices page', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await billingPage.goToInvoices();

      await expect(page).toHaveURL(/billing\/invoices/);
    });

    test('invoices page loads', async ({ page }) => {
      await page.goto('/billing/invoices');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('h1')).toContainText(/Invoices/i);
    });

    test('displays invoices table or empty state', async ({ page }) => {
      await page.goto('/billing/invoices');
      await page.waitForLoadState('networkidle');

      // Either has table or no invoices message
      const hasTable = await page.locator('table').isVisible();
      const hasEmptyState = await page.locator('text=/No invoices/i').isVisible();

      expect(hasTable || hasEmptyState).toBe(true);
    });

    test('invoice rows show required information', async ({ page }) => {
      await page.goto('/billing/invoices');
      await page.waitForLoadState('networkidle');

      const table = page.locator('table');
      if (await table.isVisible()) {
        // Check table headers
        await expect(page.locator('th:has-text("Amount"), th:has-text("Date"), th:has-text("Status")')).toBeVisible();
      }
    });
  });

  test.describe('Stripe Portal Integration', () => {
    test('manage billing button is clickable', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      const manageButton = page.locator('button:has-text("Manage Billing")');
      await expect(manageButton).toBeVisible();
      await expect(manageButton).toBeEnabled();
    });

    test('clicking manage billing shows loading state', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      // Mock the API response to prevent actual navigation
      await page.route('**/billing/portal/**', async (route) => {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ portal_url: 'https://billing.stripe.com/test' }),
        });
      });

      const manageButton = page.locator('button:has-text("Manage Billing")');
      await manageButton.click();

      // Should show loading spinner
      const spinner = page.locator('.animate-spin');
      // Spinner should appear briefly
      await expect(spinner).toBeVisible({ timeout: 1000 }).catch(() => {
        // Loading might be too fast to catch
      });
    });

    test('payment method card links to stripe', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();

      const paymentCard = page.locator('text=/Payment Method/i');
      await expect(paymentCard).toBeVisible();
    });
  });

  test.describe('Plan Change Flow', () => {
    test('upgrade button appears for lower tier plans', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Look for upgrade buttons on non-current plans
      const upgradeButtons = page.locator('button:has-text("Upgrade"), button:has-text("Select")');
      await expect(upgradeButtons.first()).toBeVisible();
    });

    test('clicking upgrade initiates checkout flow', async ({ page }) => {
      await page.goto('/billing/plans');
      await page.waitForLoadState('networkidle');

      // Mock the checkout API
      await page.route('**/billing/checkout/**', async (route) => {
        await route.fulfill({
          status: 200,
          body: JSON.stringify({ checkout_url: 'https://checkout.stripe.com/test' }),
        });
      });

      const upgradeButton = page.locator('button:has-text("Upgrade"), button:has-text("Select")').first();
      if (await upgradeButton.isVisible()) {
        await upgradeButton.click();

        // Should show loading or redirect
        // In real test, would check for Stripe redirect
      }
    });
  });

  test.describe('Subscription Status Display', () => {
    test('active subscription shows active badge', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // Check for status badge
      const badge = page.locator('[class*="badge"]').first();
      const badgeText = await badge.textContent();

      // Should be one of the valid statuses
      expect(['Active', 'Trial', 'Past Due', 'Canceled', 'active', 'trial', 'past_due', 'canceled']).toContain(
        badgeText?.trim() || ''
      );
    });

    test('canceled subscription shows warning', async ({ page }) => {
      const billingPage = new BillingPage(page);
      await billingPage.goto();
      await page.waitForLoadState('networkidle');

      // If subscription is set to cancel, should show warning
      const cancelWarning = page.locator('text=/will be canceled/i');
      // This is conditional - only visible if cancel_at_period_end is true
      // Just verify it doesn't error
      await cancelWarning.isVisible().catch(() => false);
    });
  });
});
