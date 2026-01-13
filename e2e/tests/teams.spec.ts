import { test, expect } from '@playwright/test';
import { LoginPage, DashboardPage, TeamPage } from '../pages';
import { TEST_USERS, generateTestInvitation, TEST_TEAMS } from '../fixtures/test-data';

/**
 * Team Management E2E Tests
 *
 * Tests cover:
 * - Viewing team overview
 * - Managing team members
 * - Sending invitations
 * - Changing member roles
 * - Removing members
 */

test.describe('Team Management', () => {
  // Login before each test
  test.beforeEach(async ({ page }) => {
    const loginPage = new LoginPage(page);
    await loginPage.goto();
    await loginPage.loginAndWaitForDashboard(
      TEST_USERS.owner.email,
      TEST_USERS.owner.password
    );
  });

  test.describe('Team Overview', () => {
    test('can view team overview page', async ({ page }) => {
      const dashboardPage = new DashboardPage(page);
      const teamPage = new TeamPage(page);

      await dashboardPage.navigateToTeam();
      await teamPage.assertTeamPageVisible();
    });

    test('team overview displays stats cards', async ({ page }) => {
      const teamPage = new TeamPage(page);
      await teamPage.goto();

      // Check stats cards are visible
      await expect(page.locator('text=/Total Members/i')).toBeVisible();
      await expect(page.locator('text=/Team Name/i')).toBeVisible();
      await expect(page.locator('text=/Pending Invites/i')).toBeVisible();
    });

    test('team overview has navigation links', async ({ page }) => {
      const teamPage = new TeamPage(page);
      await teamPage.goto();

      // Check navigation cards
      await expect(page.locator('a[href="/team/members"]')).toBeVisible();
      await expect(page.locator('a[href="/team/invitations"]')).toBeVisible();
      await expect(page.locator('a[href="/team/settings"]')).toBeVisible();
    });

    test('can navigate to members page from overview', async ({ page }) => {
      const teamPage = new TeamPage(page);
      await teamPage.goto();
      await teamPage.goToMembers();

      await expect(page).toHaveURL(/team\/members/);
      await expect(page.locator('h1')).toContainText(/Team Members/i);
    });

    test('can navigate to invitations page from overview', async ({ page }) => {
      const teamPage = new TeamPage(page);
      await teamPage.goto();
      await teamPage.goToInvitations();

      await expect(page).toHaveURL(/team\/invitations/);
      await expect(page.locator('h1')).toContainText(/Invitations/i);
    });
  });

  test.describe('Team Members', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');
    });

    test('displays members table', async ({ page }) => {
      const teamPage = new TeamPage(page);
      await teamPage.assertMembersTableVisible();
    });

    test('shows owner in members list', async ({ page }) => {
      // The owner should be visible in the members list
      await expect(page.locator(`text="${TEST_USERS.owner.email}"`).first()).toBeVisible();
    });

    test('owner badge is displayed for owner', async ({ page }) => {
      // Find the owner row and check for owner badge
      const ownerRow = page.locator(`tr:has-text("${TEST_USERS.owner.email}")`);
      await expect(ownerRow.locator('text=/owner/i')).toBeVisible();
    });

    test('can navigate to invite page from members', async ({ page }) => {
      await page.click('text=/Invite Member/i');
      await expect(page).toHaveURL(/team\/invitations/);
    });
  });

  test.describe('Team Invitations', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/team/invitations');
      await page.waitForLoadState('networkidle');
    });

    test('displays invitations page', async ({ page }) => {
      await expect(page.locator('h1')).toContainText(/Invitations/i);
    });

    test('can open invite member dialog', async ({ page }) => {
      await page.click('button:has-text("Invite Member")');
      await expect(page.locator('[role="dialog"]')).toBeVisible();
      await expect(page.locator('[role="dialog"] h2')).toContainText(/Invite Team Member/i);
    });

    test('can fill invite form with member role', async ({ page }) => {
      const invitation = generateTestInvitation();

      await page.click('button:has-text("Invite Member")');

      // Fill email
      await page.fill('#email', invitation.email);

      // Select member role (default)
      await expect(page.locator('button:has-text("Member")')).toBeVisible();

      // Verify description text
      await expect(page.locator('text=/Members can access team resources/i')).toBeVisible();
    });

    test('can fill invite form with admin role', async ({ page }) => {
      const invitation = generateTestInvitation();

      await page.click('button:has-text("Invite Member")');

      // Fill email
      await page.fill('#email', invitation.email);

      // Select admin role
      await page.click('button:has-text("Admin")');

      // Verify description text changes
      await expect(page.locator('text=/Admins can manage team members/i')).toBeVisible();
    });

    test('can cancel invite dialog', async ({ page }) => {
      await page.click('button:has-text("Invite Member")');
      await expect(page.locator('[role="dialog"]')).toBeVisible();

      await page.click('button:has-text("Cancel")');
      await expect(page.locator('[role="dialog"]')).not.toBeVisible();
    });

    test('invite form requires email', async ({ page }) => {
      await page.click('button:has-text("Invite Member")');

      // Try to submit without email
      await page.click('button:has-text("Send Invitation")');

      // Dialog should still be open (form validation)
      await expect(page.locator('[role="dialog"]')).toBeVisible();
    });

    test('send invitation creates pending invite', async ({ page }) => {
      const invitation = generateTestInvitation();
      const teamPage = new TeamPage(page);

      await teamPage.inviteMember(invitation.email, 'member');

      // Check invitation appears in list
      await expect(page.locator(`text="${invitation.email}"`)).toBeVisible();
      await expect(page.locator(`tr:has-text("${invitation.email}") >> text=/pending/i`)).toBeVisible();
    });

    test('can resend invitation', async ({ page }) => {
      // First create an invitation
      const invitation = generateTestInvitation();
      const teamPage = new TeamPage(page);
      await teamPage.inviteMember(invitation.email, 'member');

      // Open actions menu and resend
      const row = page.locator(`tr:has-text("${invitation.email}")`);
      await row.locator('button[aria-haspopup="menu"]').click();
      await page.click('text=/Resend Invitation/i');

      // Invitation should still be visible
      await expect(page.locator(`text="${invitation.email}"`)).toBeVisible();
    });

    test('can cancel invitation', async ({ page }) => {
      // First create an invitation
      const invitation = generateTestInvitation();
      const teamPage = new TeamPage(page);
      await teamPage.inviteMember(invitation.email, 'member');

      // Cancel the invitation
      await teamPage.cancelInvitation(invitation.email);

      // Invitation should no longer be in pending list
      await expect(page.locator(`text="${invitation.email}"`)).not.toBeVisible();
    });
  });

  test.describe('Member Role Changes', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');
    });

    test('owner cannot be demoted', async ({ page }) => {
      // Find owner row
      const ownerRow = page.locator(`tr:has-text("${TEST_USERS.owner.email}")`);

      // Check that there's no actions menu for owner
      const actionsButton = ownerRow.locator('button[aria-haspopup="menu"]');
      await expect(actionsButton).not.toBeVisible();
    });

    test('non-owner members have actions menu', async ({ page }) => {
      // If there are other members, they should have actions
      // This test assumes there are other members in the team
      const memberRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await memberRows.count();

      if (count > 0) {
        const actionsButton = memberRows.first().locator('button[aria-haspopup="menu"]');
        await expect(actionsButton).toBeVisible();
      }
    });

    test('can open member actions menu', async ({ page }) => {
      // Skip if no non-owner members
      const memberRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await memberRows.count();

      if (count > 0) {
        await memberRows.first().locator('button[aria-haspopup="menu"]').click();

        // Check menu options
        await expect(page.locator('text=/Promote to Admin|Demote to Member/i')).toBeVisible();
        await expect(page.locator('text=/Remove Member/i')).toBeVisible();
      }
    });
  });

  test.describe('Remove Member', () => {
    test.beforeEach(async ({ page }) => {
      await page.goto('/team/members');
      await page.waitForLoadState('networkidle');
    });

    test('remove member shows confirmation dialog', async ({ page }) => {
      const memberRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await memberRows.count();

      if (count > 0) {
        // Open actions menu
        await memberRows.first().locator('button[aria-haspopup="menu"]').click();

        // Click remove
        await page.click('text=/Remove Member/i');

        // Confirmation dialog should appear
        await expect(page.locator('[role="dialog"]')).toBeVisible();
        await expect(page.locator('[role="dialog"] h2')).toContainText(/Remove Team Member/i);
      }
    });

    test('can cancel remove member dialog', async ({ page }) => {
      const memberRows = page.locator('tbody tr:not(:has-text("owner"))');
      const count = await memberRows.count();

      if (count > 0) {
        // Open actions and click remove
        await memberRows.first().locator('button[aria-haspopup="menu"]').click();
        await page.click('text=/Remove Member/i');

        // Cancel
        await page.click('button:has-text("Cancel")');
        await expect(page.locator('[role="dialog"]')).not.toBeVisible();
      }
    });
  });

  test.describe('Team Settings', () => {
    test('can navigate to team settings', async ({ page }) => {
      await page.goto('/team');
      await page.click('a[href="/team/settings"]');

      await expect(page).toHaveURL(/team\/settings/);
    });

    test('team settings page loads', async ({ page }) => {
      await page.goto('/team/settings');
      await expect(page.locator('h1')).toBeVisible();
    });
  });
});
