import { test, expect } from '@playwright/test';
import { LoginPage, RegisterPage, DashboardPage, LandingPage } from '../pages';
import { TEST_USERS, generateUniqueTestUser, TEST_URLS } from '../fixtures/test-data';

/**
 * Authentication E2E Tests
 *
 * Tests cover:
 * - Complete signup flow
 * - Login with valid/invalid credentials
 * - Logout functionality
 * - Protected route access
 * - Session persistence
 */

test.describe('Authentication', () => {
  test.describe('Signup Flow', () => {
    test('complete signup flow from landing page', async ({ page }) => {
      const landingPage = new LandingPage(page);
      const registerPage = new RegisterPage(page);
      const loginPage = new LoginPage(page);

      // Step 1: Visit landing page
      await landingPage.goto();
      await landingPage.assertLandingPageVisible();

      // Step 2: Click "Start Free Trial" or signup button
      await landingPage.clickStartFreeTrial();

      // Should navigate to signup/register page
      await expect(page).toHaveURL(/signup|register/);

      // Step 3: Fill registration form
      const testUser = generateUniqueTestUser();
      await registerPage.assertFormVisible();
      await registerPage.register({
        firstName: testUser.firstName,
        lastName: testUser.lastName,
        email: testUser.email,
        password: testUser.password,
      });

      // Step 4: Verify redirect to login with success
      await expect(page).toHaveURL(/login.*registered=true/);

      // Step 5: Login with new credentials
      await loginPage.login(testUser.email, testUser.password);

      // Step 6: Verify redirect to dashboard with welcome state
      await expect(page).toHaveURL(/^\/$|dashboard/);
    });

    test('signup with valid credentials redirects to login', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      const testUser = generateUniqueTestUser();

      await registerPage.goto();
      await registerPage.assertPageTitle();
      await registerPage.assertFormVisible();

      await registerPage.registerAndWaitForLogin({
        firstName: testUser.firstName,
        lastName: testUser.lastName,
        email: testUser.email,
        password: testUser.password,
      });

      // Should be on login page with registered parameter
      await expect(page).toHaveURL(/login.*registered/);
    });

    test('signup fails with password mismatch', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      const testUser = generateUniqueTestUser();

      await registerPage.goto();
      await registerPage.register({
        firstName: testUser.firstName,
        lastName: testUser.lastName,
        email: testUser.email,
        password: 'Password123!',
        confirmPassword: 'DifferentPassword123!',
      });

      await registerPage.verifyPasswordMismatchError();
    });

    test('signup fails with short password', async ({ page }) => {
      const registerPage = new RegisterPage(page);
      const testUser = generateUniqueTestUser();

      await registerPage.goto();
      await registerPage.register({
        firstName: testUser.firstName,
        lastName: testUser.lastName,
        email: testUser.email,
        password: 'short',
        confirmPassword: 'short',
      });

      await registerPage.verifyPasswordLengthError();
    });

    test('signup form validates required fields', async ({ page }) => {
      const registerPage = new RegisterPage(page);

      await registerPage.goto();

      // Try to submit empty form
      await registerPage.submit();

      // Form should not navigate (HTML5 validation)
      await expect(page).toHaveURL(/register/);
    });

    test('can navigate from signup to login', async ({ page }) => {
      const registerPage = new RegisterPage(page);

      await registerPage.goto();
      await registerPage.clickSignIn();

      await expect(page).toHaveURL(/login/);
    });
  });

  test.describe('Login Flow', () => {
    test('login with valid credentials', async ({ page }) => {
      const loginPage = new LoginPage(page);
      const dashboardPage = new DashboardPage(page);

      await loginPage.goto();
      await loginPage.assertPageTitle();
      await loginPage.assertFormVisible();

      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      // Verify dashboard is displayed
      await dashboardPage.assertDashboardVisible();
      await dashboardPage.assertWelcomeContains(TEST_USERS.owner.firstName);
    });

    test('login with invalid credentials shows error', async ({ page }) => {
      const loginPage = new LoginPage(page);

      await loginPage.goto();
      await loginPage.login('invalid@example.com', 'wrongpassword');

      // Should show error message
      await expect(loginPage.hasLoginError()).resolves.toBe(true);
      const errorMessage = await loginPage.getLoginError();
      expect(errorMessage).toBeTruthy();
    });

    test('login with empty credentials shows validation', async ({ page }) => {
      const loginPage = new LoginPage(page);

      await loginPage.goto();
      await loginPage.submit();

      // Should not navigate (HTML5 validation)
      await expect(page).toHaveURL(/login/);
    });

    test('can navigate from login to signup', async ({ page }) => {
      const loginPage = new LoginPage(page);

      await loginPage.goto();
      await loginPage.clickSignUp();

      await expect(page).toHaveURL(/register/);
    });

    test('can navigate to forgot password', async ({ page }) => {
      const loginPage = new LoginPage(page);

      await loginPage.goto();
      await loginPage.clickForgotPassword();

      await expect(page).toHaveURL(/forgot-password/);
    });

    test('login with return URL redirects correctly', async ({ page }) => {
      const loginPage = new LoginPage(page);

      // Visit protected page that should redirect to login with returnUrl
      await page.goto(`${TEST_URLS.app}/settings`);

      // Should redirect to login
      await expect(page).toHaveURL(/login/);

      // Login
      await loginPage.login(TEST_USERS.owner.email, TEST_USERS.owner.password);

      // Should redirect back to settings
      await expect(page).toHaveURL(/settings/);
    });
  });

  test.describe('Logout Flow', () => {
    test.beforeEach(async ({ page }) => {
      // Login before each logout test
      const loginPage = new LoginPage(page);
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );
    });

    test('logout clears session and redirects to login', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);

      await dashboardPage.logout();

      // Should be on login page
      await expect(page).toHaveURL(/login/);
    });

    test('cannot access dashboard after logout', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);

      await dashboardPage.logout();

      // Try to access dashboard directly
      await page.goto(TEST_URLS.app);

      // Should redirect to login
      await expect(page).toHaveURL(/login/);
    });

    test('cannot access protected routes after logout', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);

      await dashboardPage.logout();

      // Try to access various protected routes
      const protectedRoutes = ['/team', '/billing', '/settings'];

      for (const route of protectedRoutes) {
        await page.goto(`${TEST_URLS.app}${route}`);
        await expect(page).toHaveURL(/login/);
      }
    });
  });

  test.describe('Protected Routes', () => {
    test('unauthenticated user cannot access dashboard', async ({ page }) => {
      await page.goto(TEST_URLS.app);
      await expect(page).toHaveURL(/login/);
    });

    test('unauthenticated user cannot access team page', async ({ page }) => {
      await page.goto(`${TEST_URLS.app}/team`);
      await expect(page).toHaveURL(/login/);
    });

    test('unauthenticated user cannot access billing page', async ({ page }) => {
      await page.goto(`${TEST_URLS.app}/billing`);
      await expect(page).toHaveURL(/login/);
    });

    test('unauthenticated user cannot access settings page', async ({ page }) => {
      await page.goto(`${TEST_URLS.app}/settings`);
      await expect(page).toHaveURL(/login/);
    });

    test('login and register pages are accessible without auth', async ({ page }) => {
      await page.goto(`${TEST_URLS.app}/login`);
      await expect(page).toHaveURL(/login/);
      await expect(page.locator('h1, h2').first()).toContainText(/Sign in/i);

      await page.goto(`${TEST_URLS.app}/register`);
      await expect(page).toHaveURL(/register/);
      await expect(page.locator('h1, h2').first()).toContainText(/Create an account/i);
    });
  });

  test.describe('Session Persistence', () => {
    test('session persists after page refresh', async ({ page }) => {
      const loginPage = new LoginPage(page);
      const dashboardPage = new DashboardPage(page);

      // Login
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      // Refresh page
      await page.reload();

      // Should still be on dashboard
      await dashboardPage.assertDashboardVisible();
    });

    test('session persists across navigation', async ({ page }) => {
      const loginPage = new LoginPage(page);
      const dashboardPage = new DashboardPage(page);

      // Login
      await loginPage.goto();
      await loginPage.loginAndWaitForDashboard(
        TEST_USERS.owner.email,
        TEST_USERS.owner.password
      );

      // Navigate to different pages
      await dashboardPage.navigateToTeam();
      await expect(page).toHaveURL(/team/);

      await page.goBack();
      await dashboardPage.assertDashboardVisible();

      await dashboardPage.navigateToBilling();
      await expect(page).toHaveURL(/billing/);

      await dashboardPage.navigateToSettings();
      await expect(page).toHaveURL(/settings/);
    });
  });
});
