/**
 * Test data and credentials for E2E testing.
 *
 * IMPORTANT: These are test credentials used only in local/test environments.
 * Never use production credentials here.
 */

export const TEST_URLS = {
  // Landing page
  landing: 'http://localhost:3000',

  // Dashboard application
  app: 'http://localhost:3001',

  // Backend API
  api: 'http://localhost:8000/api',
} as const;

/**
 * Test user credentials for different roles and scenarios.
 */
export const TEST_USERS = {
  owner: {
    email: 'owner@test.com',
    password: 'TestPassword123!',
    firstName: 'Test',
    lastName: 'Owner',
    role: 'owner' as const,
  },
  admin: {
    email: 'admin@test.com',
    password: 'TestPassword123!',
    firstName: 'Test',
    lastName: 'Admin',
    role: 'admin' as const,
  },
  member: {
    email: 'member@test.com',
    password: 'TestPassword123!',
    firstName: 'Test',
    lastName: 'Member',
    role: 'member' as const,
  },
  newUser: {
    email: `newuser+${Date.now()}@test.com`,
    password: 'TestPassword123!',
    firstName: 'New',
    lastName: 'User',
    companyName: 'Test Company',
  },
} as const;

/**
 * Generate unique test user data for signup tests.
 */
export function generateUniqueTestUser() {
  const timestamp = Date.now();
  return {
    email: `testuser+${timestamp}@test.com`,
    password: 'TestPassword123!',
    firstName: 'Test',
    lastName: `User${timestamp}`,
    companyName: `Test Company ${timestamp}`,
  };
}

/**
 * Test team data.
 */
export const TEST_TEAMS = {
  default: {
    name: 'Test Team',
    slug: 'test-team',
  },
  new: {
    name: 'New Test Team',
    slug: 'new-test-team',
  },
} as const;

/**
 * Test billing/subscription data.
 */
export const TEST_BILLING = {
  plans: {
    free: {
      name: 'Free',
      priceMonthly: 0,
    },
    pro: {
      name: 'Pro',
      priceMonthly: 29,
    },
    enterprise: {
      name: 'Enterprise',
      priceMonthly: 99,
    },
  },
} as const;

/**
 * Test invitation data.
 */
export function generateTestInvitation() {
  const timestamp = Date.now();
  return {
    email: `invite+${timestamp}@test.com`,
    role: 'member' as const,
  };
}

/**
 * Selectors for common UI elements.
 * Using data-testid attributes when available, falling back to accessible selectors.
 */
export const SELECTORS = {
  // Navigation
  sidebar: '[data-testid="sidebar"], nav[role="navigation"]',
  header: 'header',
  mainContent: 'main',

  // Auth forms
  loginForm: 'form',
  emailInput: 'input[type="email"], input[name="email"], #email',
  passwordInput: 'input[type="password"], input[name="password"], #password',
  submitButton: 'button[type="submit"]',

  // Common buttons
  signInButton: 'button:has-text("Sign in"), button:has-text("Login")',
  signUpButton: 'button:has-text("Sign up"), button:has-text("Create account")',
  logoutButton: 'button:has-text("Logout"), button:has-text("Sign out")',

  // Dashboard elements
  dashboardTitle: 'h1:has-text("Dashboard")',
  welcomeMessage: 'text=/Welcome/i',

  // Team elements
  teamPage: 'h1:has-text("Team")',
  inviteMemberButton: 'button:has-text("Invite Member"), button:has-text("Invite")',
  membersTable: 'table',

  // Billing elements
  billingPage: 'h1:has-text("Billing")',
  currentPlan: 'text=/Current Plan/i',
  changePlanButton: 'text=/Change Plan/i, a:has-text("Change Plan")',

  // Settings elements
  settingsPage: 'h1:has-text("Settings")',
  profileSection: 'text=/Profile/i',
  securitySection: 'text=/Security/i',
  apiKeysSection: 'text=/API Keys/i',

  // Dialogs
  dialog: '[role="dialog"]',
  dialogTitle: '[role="dialog"] h2',
  dialogCloseButton: '[role="dialog"] button:has-text("Cancel"), [role="dialog"] button:has-text("Close")',

  // Alerts and notifications
  errorAlert: '.text-destructive, [role="alert"]',
  successAlert: '.text-green-600, .bg-green-100',

  // Loading states
  loadingSpinner: '.animate-spin, [data-testid="loading"]',
} as const;

/**
 * Common wait times in milliseconds.
 */
export const TIMEOUTS = {
  short: 1000,
  medium: 3000,
  long: 5000,
  navigation: 10000,
  apiRequest: 15000,
} as const;
