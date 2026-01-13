import { chromium, FullConfig } from '@playwright/test';
import { TEST_USERS, TEST_URLS } from './fixtures/test-data';
import { STORAGE_STATE } from './fixtures/api-helpers';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Global setup for Playwright tests.
 *
 * This runs once before all tests and:
 * 1. Ensures the auth directory exists
 * 2. Creates authenticated sessions for test users
 * 3. Saves session state for reuse in tests
 *
 * This approach improves test performance by not requiring login in every test.
 */
async function globalSetup(config: FullConfig) {
  console.log('Running global setup...');

  // Ensure auth directory exists
  const authDir = path.join(__dirname, 'playwright/.auth');
  if (!fs.existsSync(authDir)) {
    fs.mkdirSync(authDir, { recursive: true });
  }

  const browser = await chromium.launch();

  // Create authenticated sessions for each test user role
  const users = [
    { user: TEST_USERS.owner, storageState: STORAGE_STATE.owner },
    { user: TEST_USERS.admin, storageState: STORAGE_STATE.admin },
    { user: TEST_USERS.member, storageState: STORAGE_STATE.member },
  ];

  for (const { user, storageState } of users) {
    try {
      console.log(`Creating authenticated session for ${user.email}...`);

      const context = await browser.newContext();
      const page = await context.newPage();

      // Navigate to login page
      await page.goto(`${TEST_URLS.app}/login`);

      // Fill login form
      await page.fill('#email', user.email);
      await page.fill('#password', user.password);

      // Submit and wait for navigation
      await page.click('button[type="submit"]');

      // Wait for successful login (dashboard load)
      try {
        await page.waitForURL('**/', { timeout: 10000 });
        await page.waitForLoadState('networkidle');

        // Verify we're on the dashboard
        const dashboardTitle = await page.locator('h1:has-text("Dashboard")').isVisible();
        if (dashboardTitle) {
          console.log(`  Successfully logged in as ${user.email}`);

          // Save storage state
          const storagePath = path.join(__dirname, storageState);
          await context.storageState({ path: storagePath });
          console.log(`  Saved storage state to ${storagePath}`);
        } else {
          console.warn(`  Warning: Could not verify dashboard for ${user.email}`);
        }
      } catch (error) {
        console.warn(`  Warning: Login may have failed for ${user.email}:`, error);
        // Still try to save any state we have
        const storagePath = path.join(__dirname, storageState);
        await context.storageState({ path: storagePath });
      }

      await context.close();
    } catch (error) {
      console.error(`Failed to create session for ${user.email}:`, error);
      // Create an empty storage state file so tests can still run
      const storagePath = path.join(__dirname, storageState);
      fs.writeFileSync(
        storagePath,
        JSON.stringify({
          cookies: [],
          origins: [],
        })
      );
    }
  }

  await browser.close();

  console.log('Global setup complete.');
}

export default globalSetup;
