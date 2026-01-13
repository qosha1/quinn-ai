import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the login page.
 */
export class LoginPage extends BasePage {
  // Selectors
  readonly emailInput = '#email';
  readonly passwordInput = '#password';
  readonly signInButton = 'button[type="submit"]';
  readonly signUpLink = 'a[href="/register"]';
  readonly forgotPasswordLink = 'a[href="/forgot-password"]';
  readonly errorMessage = '.text-destructive';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(`${TEST_URLS.app}/login`);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.emailInput);
  }

  /**
   * Fill login form with credentials.
   */
  async fillCredentials(email: string, password: string): Promise<void> {
    await this.page.fill(this.emailInput, email);
    await this.page.fill(this.passwordInput, password);
  }

  /**
   * Submit login form.
   */
  async submit(): Promise<void> {
    await this.page.click(this.signInButton);
  }

  /**
   * Perform complete login flow.
   */
  async login(email: string, password: string): Promise<void> {
    await this.fillCredentials(email, password);
    await this.submit();
  }

  /**
   * Login and wait for dashboard.
   */
  async loginAndWaitForDashboard(email: string, password: string): Promise<void> {
    await this.login(email, password);
    await this.page.waitForURL('**/');
    await this.waitForLoadingComplete();
  }

  /**
   * Click sign up link.
   */
  async clickSignUp(): Promise<void> {
    await this.page.click(this.signUpLink);
  }

  /**
   * Click forgot password link.
   */
  async clickForgotPassword(): Promise<void> {
    await this.page.click(this.forgotPasswordLink);
  }

  /**
   * Check if login error is displayed.
   */
  async hasLoginError(): Promise<boolean> {
    return this.isVisible(this.errorMessage);
  }

  /**
   * Get login error message.
   */
  async getLoginError(): Promise<string | null> {
    const error = this.page.locator(this.errorMessage);
    if (await error.isVisible()) {
      return error.textContent();
    }
    return null;
  }

  /**
   * Assert login form is visible.
   */
  async assertFormVisible(): Promise<void> {
    await expect(this.page.locator(this.emailInput)).toBeVisible();
    await expect(this.page.locator(this.passwordInput)).toBeVisible();
    await expect(this.page.locator(this.signInButton)).toBeVisible();
  }

  /**
   * Assert page title.
   */
  async assertPageTitle(): Promise<void> {
    await expect(this.page.locator('h2, h1').first()).toContainText(/Sign in/i);
  }
}
