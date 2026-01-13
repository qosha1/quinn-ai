import { Page, expect } from '@playwright/test';
import { BasePage } from './BasePage';
import { TEST_URLS } from '../fixtures/test-data';

/**
 * Page object for the team management pages.
 */
export class TeamPage extends BasePage {
  // Main team page selectors
  readonly pageTitle = 'h1:has-text("Team")';
  readonly totalMembersCard = 'text=/Total Members/i';
  readonly teamNameCard = 'text=/Team Name/i';
  readonly pendingInvitesCard = 'text=/Pending Invites/i';

  // Navigation cards
  readonly membersLink = 'a[href="/team/members"]';
  readonly invitationsLink = 'a[href="/team/invitations"]';
  readonly settingsLink = 'a[href="/team/settings"]';

  // Members page selectors
  readonly membersTable = 'table';
  readonly memberRow = 'tbody tr';
  readonly inviteMemberButton = 'button:has-text("Invite Member"), a:has-text("Invite Member")';

  // Member actions
  readonly memberActionsButton = 'button[aria-haspopup="menu"]';
  readonly promoteToAdminOption = 'text=/Promote to Admin/i';
  readonly demoteToMemberOption = 'text=/Demote to Member/i';
  readonly removeMemberOption = 'text=/Remove Member/i';

  // Invitation page selectors
  readonly inviteDialog = '[role="dialog"]';
  readonly inviteEmailInput = '#email';
  readonly memberRoleButton = 'button:has-text("Member")';
  readonly adminRoleButton = 'button:has-text("Admin")';
  readonly sendInvitationButton = 'button:has-text("Send Invitation")';
  readonly pendingInvitationsTable = 'table';

  // Invitation actions
  readonly resendInvitationOption = 'text=/Resend Invitation/i';
  readonly cancelInvitationOption = 'text=/Cancel Invitation/i';

  // Dialogs
  readonly removeDialog = '[role="dialog"]:has-text("Remove Team Member")';
  readonly confirmRemoveButton = 'button:has-text("Remove Member")';
  readonly cancelButton = 'button:has-text("Cancel")';

  constructor(page: Page) {
    super(page);
  }

  async goto(): Promise<void> {
    await this.page.goto(`${TEST_URLS.app}/team`);
  }

  async isLoaded(): Promise<boolean> {
    return this.isVisible(this.pageTitle);
  }

  /**
   * Navigate to Members page.
   */
  async goToMembers(): Promise<void> {
    await this.page.click(this.membersLink);
    await this.page.waitForURL('**/team/members');
  }

  /**
   * Navigate to Invitations page.
   */
  async goToInvitations(): Promise<void> {
    await this.page.click(this.invitationsLink);
    await this.page.waitForURL('**/team/invitations');
  }

  /**
   * Navigate to Team Settings page.
   */
  async goToSettings(): Promise<void> {
    await this.page.click(this.settingsLink);
    await this.page.waitForURL('**/team/settings');
  }

  /**
   * Get member count from the card.
   */
  async getMemberCount(): Promise<number> {
    const card = this.page.locator(this.totalMembersCard).locator('..').locator('.text-2xl');
    const text = await card.textContent();
    return parseInt(text || '0', 10);
  }

  /**
   * Open invite member dialog.
   */
  async openInviteDialog(): Promise<void> {
    await this.page.click(this.inviteMemberButton);
    await this.page.waitForSelector(this.inviteDialog);
  }

  /**
   * Invite a new member.
   */
  async inviteMember(email: string, role: 'member' | 'admin' = 'member'): Promise<void> {
    await this.openInviteDialog();
    await this.page.fill(this.inviteEmailInput, email);

    if (role === 'admin') {
      await this.page.click(this.adminRoleButton);
    } else {
      await this.page.click(this.memberRoleButton);
    }

    await this.page.click(this.sendInvitationButton);
    await this.waitForLoadingComplete();
  }

  /**
   * Check if member exists in the table by email.
   */
  async hasMember(email: string): Promise<boolean> {
    return this.isVisible(`text="${email}"`);
  }

  /**
   * Get member row by email.
   */
  getMemberRow(email: string) {
    return this.page.locator(`tr:has-text("${email}")`);
  }

  /**
   * Get member role badge.
   */
  async getMemberRole(email: string): Promise<string | null> {
    const row = this.getMemberRow(email);
    const badge = row.locator('[class*="badge"]');
    return badge.textContent();
  }

  /**
   * Open member actions menu.
   */
  async openMemberActions(email: string): Promise<void> {
    const row = this.getMemberRow(email);
    await row.locator(this.memberActionsButton).click();
  }

  /**
   * Promote member to admin.
   */
  async promoteToAdmin(email: string): Promise<void> {
    await this.openMemberActions(email);
    await this.page.click(this.promoteToAdminOption);
    await this.waitForLoadingComplete();
  }

  /**
   * Demote admin to member.
   */
  async demoteToMember(email: string): Promise<void> {
    await this.openMemberActions(email);
    await this.page.click(this.demoteToMemberOption);
    await this.waitForLoadingComplete();
  }

  /**
   * Remove a member.
   */
  async removeMember(email: string): Promise<void> {
    await this.openMemberActions(email);
    await this.page.click(this.removeMemberOption);
    await this.page.waitForSelector(this.removeDialog);
    await this.page.click(this.confirmRemoveButton);
    await this.waitForLoadingComplete();
  }

  /**
   * Check if invitation exists in the table by email.
   */
  async hasInvitation(email: string): Promise<boolean> {
    return this.isVisible(`text="${email}"`);
  }

  /**
   * Get invitation row by email.
   */
  getInvitationRow(email: string) {
    return this.page.locator(`tr:has-text("${email}")`);
  }

  /**
   * Resend invitation.
   */
  async resendInvitation(email: string): Promise<void> {
    const row = this.getInvitationRow(email);
    await row.locator(this.memberActionsButton).click();
    await this.page.click(this.resendInvitationOption);
    await this.waitForLoadingComplete();
  }

  /**
   * Cancel invitation.
   */
  async cancelInvitation(email: string): Promise<void> {
    const row = this.getInvitationRow(email);
    await row.locator(this.memberActionsButton).click();
    await this.page.click(this.cancelInvitationOption);
    await this.waitForLoadingComplete();
  }

  /**
   * Assert team page is displayed.
   */
  async assertTeamPageVisible(): Promise<void> {
    await expect(this.page.locator(this.pageTitle)).toBeVisible();
  }

  /**
   * Assert members table is visible.
   */
  async assertMembersTableVisible(): Promise<void> {
    await expect(this.page.locator(this.membersTable)).toBeVisible();
  }

  /**
   * Assert member exists with specific role.
   */
  async assertMemberHasRole(email: string, role: string): Promise<void> {
    const memberRow = this.getMemberRow(email);
    await expect(memberRow.locator(`text="${role}"`)).toBeVisible();
  }

  /**
   * Assert invitation exists.
   */
  async assertInvitationExists(email: string): Promise<void> {
    await expect(this.page.locator(`text="${email}"`)).toBeVisible();
  }

  /**
   * Assert no members message.
   */
  async assertNoMembersMessage(): Promise<void> {
    await expect(this.page.locator('text=/No team members yet/i')).toBeVisible();
  }

  /**
   * Assert no invitations message.
   */
  async assertNoInvitationsMessage(): Promise<void> {
    await expect(this.page.locator('text=/No pending invitations/i')).toBeVisible();
  }
}
