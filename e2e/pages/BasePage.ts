import { Page, Locator, expect } from '@playwright/test';
import { TIMEOUTS } from '../fixtures/test-data';

/**
 * Base page object with common functionality for all pages.
 */
export abstract class BasePage {
  protected page: Page;

  constructor(page: Page) {
    this.page = page;
  }

  /**
   * Navigate to the page URL.
   */
  abstract goto(): Promise<void>;

  /**
   * Check if the page is currently loaded.
   */
  abstract isLoaded(): Promise<boolean>;

  /**
   * Wait for the page to fully load.
   */
  async waitForLoad(): Promise<void> {
    await this.page.waitForLoadState('networkidle');
  }

  /**
   * Wait for navigation to complete.
   */
  async waitForNavigation(): Promise<void> {
    await this.page.waitForLoadState('domcontentloaded');
  }

  /**
   * Get page title.
   */
  async getTitle(): Promise<string> {
    return this.page.title();
  }

  /**
   * Get current URL.
   */
  getUrl(): string {
    return this.page.url();
  }

  /**
   * Check if element is visible.
   */
  async isVisible(selector: string): Promise<boolean> {
    try {
      await this.page.waitForSelector(selector, { state: 'visible', timeout: TIMEOUTS.short });
      return true;
    } catch {
      return false;
    }
  }

  /**
   * Wait for element to be visible.
   */
  async waitForElement(selector: string, timeout: number = TIMEOUTS.medium): Promise<Locator> {
    const element = this.page.locator(selector);
    await element.waitFor({ state: 'visible', timeout });
    return element;
  }

  /**
   * Wait for element to be hidden.
   */
  async waitForElementHidden(selector: string, timeout: number = TIMEOUTS.medium): Promise<void> {
    await this.page.waitForSelector(selector, { state: 'hidden', timeout });
  }

  /**
   * Click on an element.
   */
  async click(selector: string): Promise<void> {
    await this.page.click(selector);
  }

  /**
   * Fill an input field.
   */
  async fill(selector: string, value: string): Promise<void> {
    await this.page.fill(selector, value);
  }

  /**
   * Get text content of an element.
   */
  async getText(selector: string): Promise<string | null> {
    return this.page.textContent(selector);
  }

  /**
   * Check if error message is displayed.
   */
  async hasError(): Promise<boolean> {
    return this.isVisible('.text-destructive, [role="alert"]');
  }

  /**
   * Get error message text.
   */
  async getErrorMessage(): Promise<string | null> {
    const errorElement = this.page.locator('.text-destructive, [role="alert"]').first();
    if (await errorElement.isVisible()) {
      return errorElement.textContent();
    }
    return null;
  }

  /**
   * Check if success message is displayed.
   */
  async hasSuccess(): Promise<boolean> {
    return this.isVisible('.text-green-600, .bg-green-100');
  }

  /**
   * Get success message text.
   */
  async getSuccessMessage(): Promise<string | null> {
    const successElement = this.page.locator('.text-green-600, .bg-green-100').first();
    if (await successElement.isVisible()) {
      return successElement.textContent();
    }
    return null;
  }

  /**
   * Wait for loading spinner to disappear.
   */
  async waitForLoadingComplete(): Promise<void> {
    const spinner = this.page.locator('.animate-spin');
    if (await spinner.isVisible()) {
      await spinner.waitFor({ state: 'hidden', timeout: TIMEOUTS.apiRequest });
    }
  }

  /**
   * Take a screenshot with a descriptive name.
   */
  async screenshot(name: string): Promise<void> {
    await this.page.screenshot({ path: `screenshots/${name}.png` });
  }

  /**
   * Check if dialog is open.
   */
  async isDialogOpen(): Promise<boolean> {
    return this.isVisible('[role="dialog"]');
  }

  /**
   * Close dialog if open.
   */
  async closeDialog(): Promise<void> {
    const closeButton = this.page.locator('[role="dialog"] button:has-text("Cancel"), [role="dialog"] button:has-text("Close")');
    if (await closeButton.isVisible()) {
      await closeButton.click();
      await this.waitForElementHidden('[role="dialog"]');
    }
  }

  /**
   * Assert URL contains a path.
   */
  async assertUrlContains(path: string): Promise<void> {
    await expect(this.page).toHaveURL(new RegExp(path));
  }

  /**
   * Assert page heading text.
   */
  async assertHeading(text: string): Promise<void> {
    await expect(this.page.locator('h1').first()).toContainText(text);
  }
}
