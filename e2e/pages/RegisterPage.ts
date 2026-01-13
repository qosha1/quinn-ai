import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the registration page.
 */
export class RegisterPage extends BasePage {
  // Selectors
  readonly firstNameInput = '#firstName';
  readonly lastNameInput = '#lastName';
  readonly emailInput = '#email';
  readonly passwordInput = '#password';
  readonly confirmPasswordInput = '#confirmPassword';
  readonly createAccountButton = 'button[type="submit"]';
  readonly signInLink = 'a[href="/login"]';
  readonly errorMessage = '.text-destructive';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(`${TEST_URLS.app}/register`);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.firstNameInput);
  }

  /**
   * Fill registration form.
   */
  async fillForm(data: {
    firstName: string;
    lastName: string;
    email: string;
    password: string;
    confirmPassword?: string;
  }): Promise<void> {
    await this.page.fill(this.firstNameInput, data.firstName);
    await this.page.fill(this.lastNameInput, data.lastName);
    await this.page.fill(this.emailInput, data.email);
    await this.page.fill(this.passwordInput, data.password);
    await this.page.fill(this.confirmPasswordInput, data.confirmPassword || data.password);
  }

  /**
   * Submit registration form.
   */
  async submit(): Promise<void> {
    await this.page.click(this.createAccountButton);
  }

  /**
   * Perform complete registration flow.
   */
  async register(data: {
    firstName: string;
    lastName: string;
    email: string;
    password: string;
    confirmPassword?: string;
  }): Promise<void> {
    await this.fillForm(data);
    await this.submit();
  }

  /**
   * Register and wait for redirect to login.
   */
  async registerAndWaitForLogin(data: {
    firstName: string;
    lastName: string;
    email: string;
    password: string;
  }): Promise<void> {
    await this.register(data);
    await this.page.waitForURL('**/login*');
  }

  /**
   * Click sign in link.
   */
  async clickSignIn(): Promise<void> {
    await this.page.click(this.signInLink);
  }

  /**
   * Check if registration error is displayed.
   */
  async hasRegistrationError(): Promise<boolean> {
    return this.isVisible(this.errorMessage);
  }

  /**
   * Get registration error message.
   */
  async getRegistrationError(): Promise<string | null> {
    const error = this.page.locator(this.errorMessage);
    if (await error.isVisible()) {
      return error.textContent();
    }
    return null;
  }

  /**
   * Assert registration form is visible.
   */
  async assertFormVisible(): Promise<void> {
    await expect(this.page.locator(this.firstNameInput)).toBeVisible();
    await expect(this.page.locator(this.lastNameInput)).toBeVisible();
    await expect(this.page.locator(this.emailInput)).toBeVisible();
    await expect(this.page.locator(this.passwordInput)).toBeVisible();
    await expect(this.page.locator(this.confirmPasswordInput)).toBeVisible();
    await expect(this.page.locator(this.createAccountButton)).toBeVisible();
  }

  /**
   * Assert page title.
   */
  async assertPageTitle(): Promise<void> {
    await expect(this.page.locator('h2, h1').first()).toContainText(/Create an account/i);
  }

  /**
   * Verify password validation.
   */
  async verifyPasswordMismatchError(): Promise<void> {
    await expect(this.page.locator(this.errorMessage)).toContainText(/Passwords do not match/i);
  }

  /**
   * Verify password length error.
   */
  async verifyPasswordLengthError(): Promise<void> {
    await expect(this.page.locator(this.errorMessage)).toContainText(/at least 8 characters/i);
  }
}
