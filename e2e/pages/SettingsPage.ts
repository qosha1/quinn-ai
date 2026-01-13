import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the settings pages.
 */
export class SettingsPage extends BasePage {
  // Main settings page selectors
  readonly pageTitle = 'h1:has-text("Settings")';
  readonly profileLink = 'a[href="/settings/profile"]';
  readonly securityLink = 'a[href="/settings/security"]';
  readonly apiKeysLink = 'a[href="/settings/api-keys"]';

  // Profile page selectors
  readonly profileTitle = 'h1:has-text("Profile")';
  readonly firstNameInput = '#first_name';
  readonly lastNameInput = '#last_name';
  readonly emailInput = '#email';
  readonly saveChangesButton = 'button:has-text("Save Changes")';
  readonly avatarSection = 'text=/Avatar/i';
  readonly uploadImageButton = 'button:has-text("Upload Image")';

  // Security page selectors
  readonly securityTitle = 'h1:has-text("Security")';
  readonly currentPasswordInput = '#currentPassword';
  readonly newPasswordInput = '#newPassword';
  readonly confirmPasswordInput = '#confirmPassword';
  readonly updatePasswordButton = 'button:has-text("Update Password")';
  readonly twoFactorSection = 'text=/Two-Factor Authentication/i';
  readonly enableTwoFactorButton = 'button:has-text("Enable")';
  readonly activeSessionsSection = 'text=/Active Sessions/i';
  readonly revokeSessionButton = 'button:has-text("Revoke")';
  readonly signOutAllButton = 'button:has-text("Sign Out All Other Sessions")';

  // API Keys page selectors
  readonly apiKeysTitle = 'h1:has-text("API Keys")';
  readonly createApiKeyButton = 'button:has-text("Create API Key")';
  readonly apiKeysTable = 'table';
  readonly apiKeyRow = 'tbody tr';
  readonly keyNameInput = '#keyName';
  readonly createKeyButton = 'button:has-text("Create Key")';
  readonly deleteKeyButton = 'button[class*="destructive"]';

  // API Key dialog
  readonly createKeyDialog = '[role="dialog"]';
  readonly keyCreatedMessage = 'text=/API Key Created/i';
  readonly copyKeyButton = 'button:has-text("Copy")';
  readonly doneButton = 'button:has-text("Done")';
  readonly deleteKeyDialog = '[role="dialog"]:has-text("Delete API Key")';
  readonly confirmDeleteButton = 'button:has-text("Delete Key")';

  // Messages
  readonly successMessage = '.text-green-600, .bg-green-100';
  readonly errorMessage = '.text-destructive';
  readonly securityNotice = 'text=/Security Notice/i';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(`${TEST_URLS.app}/settings`);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.pageTitle);
  }

  /**
   * Navigate to Profile page.
   */
  async goToProfile(): Promise<void> {
    await this.page.click(this.profileLink);
    await this.page.waitForURL('**/settings/profile');
  }

  /**
   * Navigate to Security page.
   */
  async goToSecurity(): Promise<void> {
    await this.page.click(this.securityLink);
    await this.page.waitForURL('**/settings/security');
  }

  /**
   * Navigate to API Keys page.
   */
  async goToApiKeys(): Promise<void> {
    await this.page.click(this.apiKeysLink);
    await this.page.waitForURL('**/settings/api-keys');
  }

  // Profile methods
  /**
   * Update profile information.
   */
  async updateProfile(firstName: string, lastName: string): Promise<void> {
    await this.page.fill(this.firstNameInput, firstName);
    await this.page.fill(this.lastNameInput, lastName);
    await this.page.click(this.saveChangesButton);
    await this.waitForLoadingComplete();
  }

  /**
   * Get current profile values.
   */
  async getProfileValues(): Promise<{ firstName: string; lastName: string; email: string }> {
    return {
      firstName: (await this.page.inputValue(this.firstNameInput)) || '',
      lastName: (await this.page.inputValue(this.lastNameInput)) || '',
      email: (await this.page.inputValue(this.emailInput)) || '',
    };
  }

  // Security methods
  /**
   * Change password.
   */
  async changePassword(currentPassword: string, newPassword: string, confirmPassword?: string): Promise<void> {
    await this.page.fill(this.currentPasswordInput, currentPassword);
    await this.page.fill(this.newPasswordInput, newPassword);
    await this.page.fill(this.confirmPasswordInput, confirmPassword || newPassword);
    await this.page.click(this.updatePasswordButton);
    await this.waitForLoadingComplete();
  }

  /**
   * Click enable 2FA button.
   */
  async clickEnableTwoFactor(): Promise<void> {
    await this.page.click(this.enableTwoFactorButton);
  }

  /**
   * Check if 2FA is enabled.
   */
  async isTwoFactorEnabled(): Promise<boolean> {
    return this.isVisible('text=/Enabled/i');
  }

  /**
   * Revoke a session.
   */
  async revokeSession(index: number = 0): Promise<void> {
    const sessions = this.page.locator(this.revokeSessionButton);
    await sessions.nth(index).click();
  }

  /**
   * Sign out all other sessions.
   */
  async signOutAllSessions(): Promise<void> {
    await this.page.click(this.signOutAllButton);
  }

  // API Keys methods
  /**
   * Create a new API key.
   */
  async createApiKey(name: string): Promise<string | null> {
    await this.page.click(this.createApiKeyButton);
    await this.page.waitForSelector(this.createKeyDialog);
    await this.page.fill(this.keyNameInput, name);
    await this.page.click(this.createKeyButton);
    await this.waitForLoadingComplete();

    // Wait for key to be displayed
    await this.page.waitForSelector(this.keyCreatedMessage);

    // Get the key value
    const keyElement = this.page.locator('.font-mono.text-sm');
    const keyValue = await keyElement.textContent();

    // Close dialog
    await this.page.click(this.doneButton);

    return keyValue;
  }

  /**
   * Copy API key to clipboard.
   */
  async copyApiKey(): Promise<void> {
    await this.page.click(this.copyKeyButton);
  }

  /**
   * Delete an API key by name.
   */
  async deleteApiKey(name: string): Promise<void> {
    const row = this.page.locator(`tr:has-text("${name}")`);
    await row.locator(this.deleteKeyButton).click();
    await this.page.waitForSelector(this.deleteKeyDialog);
    await this.page.click(this.confirmDeleteButton);
    await this.waitForLoadingComplete();
  }

  /**
   * Get API key count.
   */
  async getApiKeyCount(): Promise<number> {
    const rows = this.page.locator(this.apiKeyRow);
    const count = await rows.count();
    // Subtract 1 if there's a "no keys" message row
    const noKeysMessage = await this.isVisible('text=/No API keys yet/i');
    return noKeysMessage ? 0 : count;
  }

  /**
   * Check if API key exists.
   */
  async hasApiKey(name: string): Promise<boolean> {
    return this.isVisible(`text="${name}"`);
  }

  // Assertions
  /**
   * Assert settings page is displayed.
   */
  async assertSettingsPageVisible(): Promise<void> {
    await expect(this.page.locator(this.pageTitle)).toBeVisible();
  }

  /**
   * Assert profile page is displayed.
   */
  async assertProfilePageVisible(): Promise<void> {
    await expect(this.page.locator(this.profileTitle)).toBeVisible();
  }

  /**
   * Assert security page is displayed.
   */
  async assertSecurityPageVisible(): Promise<void> {
    await expect(this.page.locator(this.securityTitle)).toBeVisible();
  }

  /**
   * Assert API keys page is displayed.
   */
  async assertApiKeysPageVisible(): Promise<void> {
    await expect(this.page.locator(this.apiKeysTitle)).toBeVisible();
  }

  /**
   * Assert profile saved success message.
   */
  async assertProfileSaved(): Promise<void> {
    await expect(this.page.locator(this.successMessage)).toContainText(/Profile updated/i);
  }

  /**
   * Assert password changed success message.
   */
  async assertPasswordChanged(): Promise<void> {
    await expect(this.page.locator(this.successMessage)).toContainText(/Password changed/i);
  }

  /**
   * Assert API key created message.
   */
  async assertApiKeyCreated(): Promise<void> {
    await expect(this.page.locator(this.keyCreatedMessage)).toBeVisible();
  }

  /**
   * Assert API key deleted (no longer in list).
   */
  async assertApiKeyDeleted(name: string): Promise<void> {
    await expect(this.page.locator(`text="${name}"`)).not.toBeVisible();
  }

  /**
   * Assert password mismatch error.
   */
  async assertPasswordMismatchError(): Promise<void> {
    await expect(this.page.locator(this.errorMessage)).toContainText(/do not match/i);
  }

  /**
   * Assert password too short error.
   */
  async assertPasswordTooShortError(): Promise<void> {
    await expect(this.page.locator(this.errorMessage)).toContainText(/at least 8 characters/i);
  }
}
