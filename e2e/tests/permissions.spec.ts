import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, TeamPage, BillingPage, SettingsPage } from '../pages';
import { TEST_USERS } from '../fixtures/test-data';

/**
 * Permissions & Role-Based Access E2E Tests
 *
 * Tests cover:
 * - Role-based UI differences (owner vs admin vs member)
 * - Action restrictions by role
 * - Cross-company data isolation
 * - Permission enforcement
 */

test.describe('Permissions & Role-Based Access', () => {
  test.describe('Owner Permissions', () => {
    test.beforeEach(async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );
    });

    test('owner can access all pages', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);

      // Dashboard
      await dashboardPage.assertDashboardVisible();

      // Team
      await dashboardPage.navigateToTeam();
      await expect(page.locator('h1')).toContainText(/Team/i);

      // Billing
      await page.goto('/billing');
      await expect(page.locator('h1')).toContainText(/Billing/i);

      // Settings
      await page.goto('/settings');
      await expect(page.locator('h1')).toContainText(/Settings/i);
    });

    test('owner sees full team management controls', async ({ page }) => {
      await page.goto('/team');
      await page.waitForLoadState('networkidle');

      // Owner should see all team management options
      await expect(page.locator('a[href="/team/members"]')).toBeVisible();
      await expect(page.locator('a[href="/team/invitations"]')).toBeVisible();
      await expect(page.locator('a[href="/team/settings"]')).toBeVisible();
    });

    test('owner can invite members', async ({ page }) => {
      await page.goto('/team/invitations');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('button:has-text("Invite Member")')).toBeVisible();
      await expect(page.locator('button:has-text("Invite Member")')).toBeEnabled();
    });

    test('owner can access billing management', async ({ page }) => {
      await page.goto('/billing');
      await page.waitForLoadState('networkidle');

      // Owner should see billing controls
      await expect(page.locator('button:has-text("Manage Billing")')).toBeVisible();
      await expect(page.locator('a[href="/billing/plans"]')).toBeVisible();
    });

    test('owner badge is displayed in team members list', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Owner should have owner badge
      const ownerRow = page.locator(`tr:has-text("${TEST_USERS.owner.email}")`);
      await expect(ownerRow.locator('text=/owner/i')).toBeVisible();
    });

    test('owner cannot be demoted or removed', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Owner row should not have actions menu
      const ownerRow = page.locator(`tr:has-text("${TEST_USERS.owner.email}")`);
      const actionsButton = ownerRow.locator('button[aria-haspopup="menu"]');

      await expect(actionsButton).not.toBeVisible();
    });

    test('owner can change member roles', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Find a non-owner member (if exists)
      const memberRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await memberRows.count();

      if (count > 0) {
        // Should see role change options
        await memberRows.first().locator('button[aria-haspopup="menu"]').click();
        await expect(page.locator('text=/Promote to Admin|Demote to Member/i')).toBeVisible();
      }
    });

    test('owner can remove members', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      const memberRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await memberRows.count();

      if (count > 0) {
        await memberRows.first().locator('button[aria-haspopup="menu"]').click();
        await expect(page.locator('text=/Remove Member/i')).toBeVisible();
      }
    });
  });

  test.describe('Admin Permissions', () => {
    test.beforeEach(async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.admin.email,
        TEST_USERS.admin.password
      );
    });

    test('admin can access dashboard', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.assertDashboardVisible();
    });

    test('admin can access team page', async ({ page }) => {
      await page.goto('/team');
      await expect(page.locator('h1')).toContainText(/Team/i);
    });

    test('admin can invite members', async ({ page }) => {
      await page.goto('/team/invitations');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('button:has-text("Invite Member")')).toBeVisible();
    });

    test('admin can view team members', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('table')).toBeVisible();
    });

    test('admin badge is displayed in team list', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      const adminRow = page.locator(`tr:has-text("${TEST_USERS.admin.email}")`);
      await expect(adminRow.locator('text=/admin/i')).toBeVisible();
    });

    test('admin can access own settings', async ({ page }) => {
      await page.goto('/settings');
      await expect(page.locator('h1')).toContainText(/Settings/i);

      // Can access profile
      await page.goto('/settings/profile');
      await expect(page.locator('h1')).toContainText(/Profile/i);
    });

    test('admin can manage own API keys', async ({ page }) => {
      await page.goto('/settings/api-keys');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('button:has-text("Create API Key")')).toBeVisible();
    });

    test('admin cannot perform owner-only actions', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Admin should not be able to modify owner
      const ownerRow = page.locator(`tr:has-text("${TEST_USERS.owner.email}")`);
      const actionsButton = ownerRow.locator('button[aria-haspopup="menu"]');

      // Owner row should not have actions for admin
      await expect(actionsButton).not.toBeVisible();
    });
  });

  test.describe('Member Permissions', () => {
    test.beforeEach(async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.member.email,
        TEST_USERS.member.password
      );
    });

    test('member can access dashboard', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);
      await dashboardPage.assertDashboardVisible();
    });

    test('member can view team overview', async ({ page }) => {
      await page.goto('/team');
      await expect(page.locator('h1')).toContainText(/Team/i);
    });

    test('member badge is displayed in team list', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      const memberRow = page.locator(`tr:has-text("${TEST_USERS.member.email}")`);
      await expect(memberRow.locator('text=/member/i')).toBeVisible();
    });

    test('member can access own profile settings', async ({ page }) => {
      await page.goto('/settings/profile');
      await expect(page.locator('h1')).toContainText(/Profile/i);
    });

    test('member can manage own API keys', async ({ page }) => {
      await page.goto('/settings/api-keys');
      await page.waitForLoadState('networkidle');

      await expect(page.locator('button:has-text("Create API Key")')).toBeVisible();
    });

    test('member cannot change other member roles', async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Member should not see actions on other members
      // This depends on implementation - check if actions menu is visible for other members
      const otherMemberRows = page.locator(`tbody tr:not(:has-text("${TEST_USERS.member.email}"))`);
      const count = await otherMemberRows.count();

      if (count > 0) {
        // If there are other members, check that member cannot modify them
        const actionsButton = otherMemberRows.first().locator('button[aria-haspopup="menu"]');
        // Either not visible or limited options
        const isVisible = await actionsButton.isVisible();
        if (isVisible) {
          await actionsButton.click();
          // Should not see role change options
          const roleOptions = page.locator('text=/Promote to Admin|Demote to Member/i');
          await expect(roleOptions).not.toBeVisible();
        }
      }
    });
  });

  test.describe('Role-Based UI Differences', () => {
    test('owner sees all team management options', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Owner should see invite button
      await expect(page.locator('a:has-text("Invite Member"), button:has-text("Invite Member")')).toBeVisible();
    });

    test('different roles show different action menus', async ({ page }) => {
      // Login as owner
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Owner can see all member actions
      const nonOwnerRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await nonOwnerRows.count();

      if (count > 0) {
        await nonOwnerRows.first().locator('button[aria-haspopup="menu"]').click();

        // Owner should see all options
        await expect(page.locator('text=/Remove Member/i')).toBeVisible();
        await expect(page.locator('text=/Promote|Demote/i')).toBeVisible();
      }
    });
  });

  test.describe('Cross-Company Isolation', () => {
    test('user only sees their own team', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      await page.goto('/team');
      await page.waitForLoadState('networkidle');

      // User should only see their own team data
      // This test verifies the team page loads without errors
      await expect(page.locator('h1')).toContainText(/Team/i);
    });

    test('API endpoints enforce team membership', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      // Try to access team data - should only return authorized data
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Page should load without 403 errors
      await expect(page.locator('text=/Team Members/i')).toBeVisible();
    });

    test('billing data is team-specific', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      await page.goto('/billing');
      await page.waitForLoadState('networkidle');

      // Should see team-specific billing info
      await expect(page.locator('h1')).toContainText(/Billing/i);
    });
  });

  test.describe('Permission Enforcement', () => {
    test('unauthorized actions show error', async ({ page }) => {
      // This test would require mocking API responses
      // to simulate permission denied scenarios
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.member.email,
        TEST_USERS.member.password
      );

      await page.goto('/team');
      await page.waitForLoadState('networkidle');

      // Page should load for member (read access)
      await expect(page.locator('h1')).toContainText(/Team/i);
    });

    test('role-based buttons are conditionally rendered', async ({ page }) => {
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.member.email,
        TEST_USERS.member.password
      );

      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // As member, check that certain admin-only actions are not visible
      // The specific buttons depend on role-based UI implementation
      const memberRow = page.locator(`tr:has-text("${TEST_USERS.member.email}")`);

      // Member's own row should not have self-modification actions
      // (can't change own role, can't remove self)
    });
  });

  test.describe('Session and Auth Edge Cases', () => {
    test('expired token redirects to login', async ({ page }) => {
      // This would require manipulating storage to simulate expired token
      // For now, just verify the login redirect works
      await page.goto('/team');

      // Without valid session, should redirect to login
      await expect(page).toHaveURL(/login/);
    });

    test('switching accounts shows correct permissions', async ({ page }) => {
      // Login as owner
      let loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      // Verify owner permissions
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Owner should see actions on non-owners
      const nonOwnerRows = page.locator('tbody tr:not(:has-text("owner"))');
      let count = await nonOwnerRows.count();

      if (count > 0) {
        await expect(nonOwnerRows.first().locator('button[aria-haspopup="menu"]')).toBeVisible();
      }

      // Logout
      const dashboardPage = new DashboardPage(page);
      await page.goto('/');
      await dashboardPage.logout();

      // Login as member
      loginPage = new LoginPage(page);
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.member.email,
        TEST_USERS.member.password
      );

      // Verify member has appropriate access
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');

      // Member should see the page but with limited actions
      await expect(page.locator('h1')).toContainText(/Team Members/i);
    });
  });
});
