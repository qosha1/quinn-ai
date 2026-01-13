import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the landing page.
 */
export class LandingPage extends BasePage {
  // Hero section
  readonly heroTitle = 'h1';
  readonly startFreeTrialButton = 'a:has-text("Start Free Trial"), button:has-text("Start Free Trial")';
  readonly seeHowItWorksButton = 'a:has-text("See How It Works")';

  // Navigation
  readonly header = 'header';
  readonly featuresLink = 'a[href="#features"]';
  readonly pricingLink = 'a[href="/pricing"], a[href="#pricing"]';

  // Features section
  readonly featuresSection = '#features, [id="features"]';
  readonly featureCards = '.feature-card, [class*="feature"]';

  // Pricing section
  readonly pricingSection = '#pricing, [id="pricing"]';
  readonly pricingCards = '.pricing-card, [class*="pricing"]';

  // Testimonials section
  readonly testimonialsSection = 'text=/Testimonials/i, text=/What our customers say/i';

  // FAQ section
  readonly faqSection = 'text=/FAQ/i, text=/Frequently Asked/i';

  // CTA section
  readonly ctaSection = 'text=/Get Started/i, text=/Ready to/i';
  readonly ctaButton = 'a:has-text("Get Started"), button:has-text("Get Started")';

  // Footer
  readonly footer = 'footer';
  readonly privacyPolicyLink = 'a[href="/privacy-policy"]';
  readonly termsOfServiceLink = 'a[href="/terms-of-service"]';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(TEST_URLS.landing);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.heroTitle);
  }

  /**
   * Click Start Free Trial button.
   */
  async clickStartFreeTrial(): Promise<void> {
    await this.page.click(this.startFreeTrialButton);
  }

  /**
   * Click See How It Works button.
   */
  async clickSeeHowItWorks(): Promise<void> {
    await this.page.click(this.seeHowItWorksButton);
  }

  /**
   * Navigate to Features section.
   */
  async goToFeatures(): Promise<void> {
    await this.page.click(this.featuresLink);
  }

  /**
   * Navigate to Pricing page or section.
   */
  async goToPricing(): Promise<void> {
    await this.page.click(this.pricingLink);
  }

  /**
   * Get hero title text.
   */
  async getHeroTitle(): Promise<string | null> {
    return this.getText(this.heroTitle);
  }

  /**
   * Check if features section is visible.
   */
  async isFeaturesVisible(): Promise<boolean> {
    return this.isVisible(this.featuresSection);
  }

  /**
   * Check if pricing section is visible.
   */
  async isPricingVisible(): Promise<boolean> {
    return this.isVisible(this.pricingSection);
  }

  /**
   * Scroll to features section.
   */
  async scrollToFeatures(): Promise<void> {
    const section = this.page.locator(this.featuresSection);
    await section.scrollIntoViewIfNeeded();
  }

  /**
   * Scroll to pricing section.
   */
  async scrollToPricing(): Promise<void> {
    const section = this.page.locator(this.pricingSection);
    await section.scrollIntoViewIfNeeded();
  }

  /**
   * Click privacy policy link.
   */
  async clickPrivacyPolicy(): Promise<void> {
    await this.page.click(this.privacyPolicyLink);
    await this.page.waitForURL('**/privacy-policy');
  }

  /**
   * Click terms of service link.
   */
  async clickTermsOfService(): Promise<void> {
    await this.page.click(this.termsOfServiceLink);
    await this.page.waitForURL('**/terms-of-service');
  }

  /**
   * Click CTA button in footer/CTA section.
   */
  async clickCtaButton(): Promise<void> {
    await this.page.click(this.ctaButton);
  }

  // Assertions
  /**
   * Assert landing page is displayed.
   */
  async assertLandingPageVisible(): Promise<void> {
    await expect(this.page.locator(this.heroTitle)).toBeVisible();
  }

  /**
   * Assert hero section content.
   */
  async assertHeroContent(): Promise<void> {
    await expect(this.page.locator(this.heroTitle)).toContainText(/Build|SaaS|Business/i);
    await expect(this.page.locator(this.startFreeTrialButton)).toBeVisible();
  }

  /**
   * Assert features section is visible.
   */
  async assertFeaturesVisible(): Promise<void> {
    await expect(this.page.locator(this.featuresSection).first()).toBeVisible();
  }

  /**
   * Assert footer is visible.
   */
  async assertFooterVisible(): Promise<void> {
    await expect(this.page.locator(this.footer)).toBeVisible();
  }

  /**
   * Assert header navigation is visible.
   */
  async assertHeaderVisible(): Promise<void> {
    await expect(this.page.locator(this.header)).toBeVisible();
  }

  /**
   * Assert highlights are displayed.
   */
  async assertHighlightsVisible(): Promise<void> {
    await expect(this.page.locator('text=/No credit card required/i')).toBeVisible();
    await expect(this.page.locator('text=/14-day free trial/i')).toBeVisible();
    await expect(this.page.locator('text=/Cancel anytime/i')).toBeVisible();
  }
}
