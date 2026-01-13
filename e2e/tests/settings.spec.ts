import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, SettingsPage } from '../pages';
import { TEST_USERS } from '../fixtures/test-data';

/**
 * Settings E2E Tests
 *
 * Tests cover:
 * - Settings navigation
 * - Profile updates
 * - Password changes
 * - API key management
 * - Security settings
 */

test.describe('Settings', () => {
  // Login before each test
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAndWaitForDashboard(
      TEST_USERS.owner.email,
      TEST_USERS.owner.password
    );
  });

  test.describe('Settings Navigation', () => {
    test('can navigate to settings from dashboard', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);
      const settingsPage = new SettingsPage(page);

      await dashboardPage.navigateToSettings();
      await settingsPage.assertSettingsPageVisible();
    });

    test('settings page displays navigation cards', async ({ page }) => {
      const settingsPage = new SettingsPage(page);
      await settingsPage.goto();

      // Check all navigation cards are visible
      await expect(page.locator('a[href="/settings/profile"]')).toBeVisible();
      await expect(page.locator('a[href="/settings/security"]')).toBeVisible();
      await expect(page.locator('a[href="/settings/api-keys"]')).toBeVisible();
    });

    test('can navigate to profile settings', async ({ page }) => {
      const settingsPage = new SettingsPage(page);
      await settingsPage.goto();
      await settingsPage.goToProfile();

      await settingsPage.assertProfilePageVisible();
    });

    test('can navigate to security settings', async ({ page }) => {
      const settingsPage = new SettingsPage(page);
      await settingsPage.goto();
      await settingsPage.goToSecurity();

      await settingsPage.assertSecurityPageVisible();
    });

    test('can navigate to API keys settings', async ({ page }) => {
      const settingsPage = new SettingsPage(page);
      await settingsPage.goto();
      await settingsPage.goToApiKeys();

      await settingsPage.assertApiKeysPageVisible();
    });
  });

  test.describe('Profile Settings', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/settings/profile');
      await page.waitForLoadState('networkidle');
    });

    test('profile page displays user information', async ({ page }) => {
      // Check form fields exist
      await expect(page.locator('#first_name')).toBeVisible();
      await expect(page.locator('#last_name')).toBeVisible();
      await expect(page.locator('#email')).toBeVisible();
    });

    test('profile fields are pre-filled with current values', async ({ page }) => {
      const settingsPage = new SettingsPage(page);

      const values = await settingsPage.getProfileValues();

      // Values should not be empty
      expect(values.email).toBeTruthy();
    });

    test('email field is disabled', async ({ page }) => {
      const emailInput = page.locator('#email');
      await expect(emailInput).toBeDisabled();
    });

    test('can update profile name', async ({ page }) => {
      const settingsPage = new SettingsPage(page);

      const newFirstName = 'Updated';
      const newLastName = 'Name';

      await settingsPage.updateProfile(newFirstName, newLastName);

      // Check success message
      await settingsPage.assertProfileSaved();
    });

    test('avatar section is displayed', async ({ page }) => {
      await expect(page.locator('text=/Avatar/i')).toBeVisible();
      await expect(page.locator('button:has-text("Upload Image")')).toBeVisible();
    });

    test('save changes button is visible', async ({ page }) => {
      await expect(page.locator('button:has-text("Save Changes")')).toBeVisible();
    });
  });

  test.describe('Security Settings', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/settings/security');
      await page.waitForLoadState('networkidle');
    });

    test('security page displays password change form', async ({ page }) => {
      await expect(page.locator('#currentPassword')).toBeVisible();
      await expect(page.locator('#newPassword')).toBeVisible();
      await expect(page.locator('#confirmPassword')).toBeVisible();
    });

    test('password form has update button', async ({ page }) => {
      await expect(page.locator('button:has-text("Update Password")')).toBeVisible();
    });

    test('password mismatch shows error', async ({ page }) => {
      const settingsPage = new SettingsPage(page);

      await settingsPage.changePassword('currentpass', 'newpass123', 'differentpass');

      await settingsPage.assertPasswordMismatchError();
    });

    test('short password shows error', async ({ page }) => {
      const settingsPage = new SettingsPage(page);

      await settingsPage.changePassword('currentpass', 'short', 'short');

      await settingsPage.assertPasswordTooShortError();
    });

    test('two-factor authentication section is displayed', async ({ page }) => {
      await expect(page.locator('text=/Two-Factor Authentication/i')).toBeVisible();
      await expect(page.locator('button:has-text("Enable")')).toBeVisible();
    });

    test('2FA status shows not enabled by default', async ({ page }) => {
      await expect(page.locator('text=/Not Enabled/i')).toBeVisible();
    });

    test('active sessions section is displayed', async ({ page }) => {
      await expect(page.locator('text=/Active Sessions/i')).toBeVisible();
    });

    test('current session is marked as active', async ({ page }) => {
      await expect(page.locator('text=/Current Session/i')).toBeVisible();
      await expect(page.locator('text=/Active/i')).toBeVisible();
    });

    test('sign out all sessions button is visible', async ({ page }) => {
      await expect(page.locator('button:has-text("Sign Out All Other Sessions")')).toBeVisible();
    });
  });

  test.describe('API Keys Settings', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/settings/api-keys');
      await page.waitForLoadState('networkidle');
    });

    test('API keys page displays create button', async ({ page }) => {
      await expect(page.locator('button:has-text("Create API Key")')).toBeVisible();
    });

    test('security notice is displayed', async ({ page }) => {
      await expect(page.locator('text=/Security Notice/i')).toBeVisible();
    });

    test('can open create API key dialog', async ({ page }) => {
      await page.click('button:has-text("Create API Key")');

      await expect(page.locator('[role="dialog"]')).toBeVisible();
      await expect(page.locator('[role="dialog"] h2')).toContainText(/Create API Key/i);
    });

    test('create key dialog has name input', async ({ page }) => {
      await page.click('button:has-text("Create API Key")');

      await expect(page.locator('#keyName')).toBeVisible();
    });

    test('can cancel create key dialog', async ({ page }) => {
      await page.click('button:has-text("Create API Key")');
      await expect(page.locator('[role="dialog"]')).toBeVisible();

      await page.click('button:has-text("Cancel")');
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test('key name is required', async ({ page }) => {
      await page.click('button:has-text("Create API Key")');

      // Try to submit without name
      await page.click('button:has-text("Create Key")');

      // Dialog should still be open (form validation)
      await expect(page.locator('[role="dialog"]')).toBeVisible();
    });

    test('can create new API key', async ({ page }) => {
      const keyName = `Test Key ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      // Wait for key creation
      await page.waitForLoadState('networkidle');

      // Should show key created message
      await expect(page.locator('text=/API Key Created/i')).toBeVisible();
    });

    test('created key shows copy button', async ({ page }) => {
      const keyName = `Test Key ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');

      // Should show copy button
      await expect(page.locator('button:has-text("Copy")')).toBeVisible();
    });

    test('can close create dialog after key creation', async ({ page }) => {
      const keyName = `Test Key ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');

      // Click done
      await page.click('button:has-text("Done")');
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test('new key appears in table', async ({ page }) => {
      const keyName = `Test Key ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');
      await page.click('button:has-text("Done")');

      // Key should appear in table
      await expect(page.locator(`text="${keyName}"`)).toBeVisible();
    });

    test('API key table shows key prefix', async ({ page }) => {
      // Create a key first
      const keyName = `Test Key ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');
      await page.click('button:has-text("Done")');

      // Check for key prefix in table (shows partial key like "sk_...")
      const keyRow = page.locator(`tr:has-text("${keyName}")`);
      await expect(keyRow.locator('code')).toBeVisible();
    });

    test('can delete API key', async ({ page }) => {
      // First create a key
      const keyName = `Delete Test ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');
      await page.click('button:has-text("Done")');

      // Now delete it
      const keyRow = page.locator(`tr:has-text("${keyName}")`);
      await keyRow.locator('button[class*="destructive"]').click();

      // Confirm deletion
      await expect(page.locator('[role="dialog"]:has-text("Delete API Key")')).toBeVisible();
      await page.click('button:has-text("Delete Key")');

      await page.waitForLoadState('networkidle');

      // Key should no longer be visible
      await expect(page.locator(`text="${keyName}"`)).not.toBeVisible();
    });

    test('delete confirmation shows key name', async ({ page }) => {
      // Create a key
      const keyName = `Confirm Delete ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');
      await page.click('button:has-text("Done")');

      // Click delete
      const keyRow = page.locator(`tr:has-text("${keyName}")`);
      await keyRow.locator('button[class*="destructive"]').click();

      // Check dialog shows key name
      await expect(page.locator('[role="dialog"]')).toContainText(keyName);
    });

    test('can cancel delete key dialog', async ({ page }) => {
      // Create a key
      const keyName = `Cancel Delete ${Date.now()}`;

      await page.click('button:has-text("Create API Key")');
      await page.fill('#keyName', keyName);
      await page.click('button:has-text("Create Key")');

      await page.waitForLoadState('networkidle');
      await page.click('button:has-text("Done")');

      // Click delete then cancel
      const keyRow = page.locator(`tr:has-text("${keyName}")`);
      await keyRow.locator('button[class*="destructive"]').click();

      await page.click('button:has-text("Cancel")');
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();

      // Key should still be visible
      await expect(page.locator(`text="${keyName}"`)).toBeVisible();
    });

    test('empty state shows when no keys', async ({ page }) => {
      // This test assumes the user has no API keys
      // Check for empty state or table
      const hasKeys = await page.locator('tbody tr').count();
      const emptyMessage = page.locator('text=/No API keys yet/i');

      if (hasKeys === 0) {
        await expect(emptyMessage).toBeVisible();
      }
    });
  });
});
