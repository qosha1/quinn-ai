import { APIRequestContext, expect } from '@playwright/test';
import { TEST_URLS, TEST_USERS } from './test-data';

/**
 * API helpers for seeding test data and managing test state.
 */

interface TokenPair {
  access: string;
  refresh: string;
}

interface User {
  id: string;
  email: string;
  first_name: string;
  last_name: string;
}

interface Team {
  id: string;
  name: string;
  slug: string;
}

interface TeamMember {
  id: string;
  user: User;
  role: 'owner' | 'admin' | 'member';
}

interface Invitation {
  id: string;
  email: string;
  role: 'admin' | 'member';
  status: 'pending' | 'accepted' | 'expired';
}

/**
 * API client for test data operations.
 */
export class ApiTestHelper {
  private request: APIRequestContext;
  private baseUrl: string;
  private tokens: TokenPair | null = null;

  constructor(request: APIRequestContext) {
    this.request = request;
    this.baseUrl = TEST_URLS.api;
  }

  /**
   * Login and store tokens for subsequent requests.
   */
  async login(email: string, password: string): Promise<TokenPair> {
    const response = await this.request.post(`${this.baseUrl}/auth/token/`, {
      data: { email, password },
    });

    expect(response.ok(), `Login failed for ${email}`).toBeTruthy();
    this.tokens = await response.json();
    return this.tokens!;
  }

  /**
   * Login as the test owner user.
   */
  async loginAsOwner(): Promise<TokenPair> {
    return this.login(TEST_USERS.owner.email, TEST_USERS.owner.password);
  }

  /**
   * Login as the test admin user.
   */
  async loginAsAdmin(): Promise<TokenPair> {
    return this.login(TEST_USERS.admin.email, TEST_USERS.admin.password);
  }

  /**
   * Login as the test member user.
   */
  async loginAsMember(): Promise<TokenPair> {
    return this.login(TEST_USERS.member.email, TEST_USERS.member.password);
  }

  /**
   * Get authorization headers.
   */
  private getAuthHeaders(): { Authorization: string } {
    if (!this.tokens) {
      throw new Error('Not authenticated. Call login() first.');
    }
    return { Authorization: `Bearer ${this.tokens.access}` };
  }

  /**
   * Register a new user.
   */
  async registerUser(data: {
    email: string;
    password: string;
    first_name: string;
    last_name: string;
  }): Promise<void> {
    const response = await this.request.post(`${this.baseUrl}/auth/register/`, {
      data,
    });
    expect(response.ok(), 'Registration failed').toBeTruthy();
  }

  /**
   * Get current user info.
   */
  async getCurrentUser(): Promise<User> {
    const response = await this.request.get(`${this.baseUrl}/users/me/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to get current user').toBeTruthy();
    return response.json();
  }

  /**
   * Get all teams for the current user.
   */
  async getTeams(): Promise<Team[]> {
    const response = await this.request.get(`${this.baseUrl}/teams/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to get teams').toBeTruthy();
    return response.json();
  }

  /**
   * Create a new team.
   */
  async createTeam(name: string): Promise<Team> {
    const response = await this.request.post(`${this.baseUrl}/teams/`, {
      headers: this.getAuthHeaders(),
      data: { name },
    });
    expect(response.ok(), 'Failed to create team').toBeTruthy();
    return response.json();
  }

  /**
   * Delete a team.
   */
  async deleteTeam(teamId: string): Promise<void> {
    const response = await this.request.delete(`${this.baseUrl}/teams/${teamId}/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to delete team').toBeTruthy();
  }

  /**
   * Get team members.
   */
  async getTeamMembers(teamId: string): Promise<TeamMember[]> {
    const response = await this.request.get(`${this.baseUrl}/teams/${teamId}/members/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to get team members').toBeTruthy();
    return response.json();
  }

  /**
   * Update a team member's role.
   */
  async updateMemberRole(teamId: string, memberId: string, role: string): Promise<TeamMember> {
    const response = await this.request.patch(
      `${this.baseUrl}/teams/${teamId}/members/${memberId}/`,
      {
        headers: this.getAuthHeaders(),
        data: { role },
      }
    );
    expect(response.ok(), 'Failed to update member role').toBeTruthy();
    return response.json();
  }

  /**
   * Remove a team member.
   */
  async removeMember(teamId: string, memberId: string): Promise<void> {
    const response = await this.request.delete(
      `${this.baseUrl}/teams/${teamId}/members/${memberId}/`,
      {
        headers: this.getAuthHeaders(),
      }
    );
    expect(response.ok(), 'Failed to remove member').toBeTruthy();
  }

  /**
   * Get team invitations.
   */
  async getInvitations(teamId: string): Promise<Invitation[]> {
    const response = await this.request.get(`${this.baseUrl}/teams/${teamId}/invitations/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to get invitations').toBeTruthy();
    return response.json();
  }

  /**
   * Create a team invitation.
   */
  async createInvitation(teamId: string, email: string, role: string): Promise<Invitation> {
    const response = await this.request.post(`${this.baseUrl}/teams/${teamId}/invitations/`, {
      headers: this.getAuthHeaders(),
      data: { email, role },
    });
    expect(response.ok(), 'Failed to create invitation').toBeTruthy();
    return response.json();
  }

  /**
   * Cancel a team invitation.
   */
  async cancelInvitation(teamId: string, invitationId: string): Promise<void> {
    const response = await this.request.delete(
      `${this.baseUrl}/teams/${teamId}/invitations/${invitationId}/`,
      {
        headers: this.getAuthHeaders(),
      }
    );
    expect(response.ok(), 'Failed to cancel invitation').toBeTruthy();
  }

  /**
   * Create an API key.
   */
  async createApiKey(name: string): Promise<{ id: string; name: string; key: string }> {
    const response = await this.request.post(`${this.baseUrl}/users/me/api-keys/`, {
      headers: this.getAuthHeaders(),
      data: { name },
    });
    expect(response.ok(), 'Failed to create API key').toBeTruthy();
    return response.json();
  }

  /**
   * Delete an API key.
   */
  async deleteApiKey(keyId: string): Promise<void> {
    const response = await this.request.delete(`${this.baseUrl}/users/me/api-keys/${keyId}/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to delete API key').toBeTruthy();
  }

  /**
   * Get subscription info.
   */
  async getSubscription(): Promise<unknown> {
    const response = await this.request.get(`${this.baseUrl}/billing/subscription/`, {
      headers: this.getAuthHeaders(),
    });
    // May return 404 if no subscription
    return response.ok() ? response.json() : null;
  }

  /**
   * Get available plans.
   */
  async getPlans(): Promise<unknown[]> {
    const response = await this.request.get(`${this.baseUrl}/billing/plans/`, {
      headers: this.getAuthHeaders(),
    });
    expect(response.ok(), 'Failed to get plans').toBeTruthy();
    return response.json();
  }

  /**
   * Clean up test data - use carefully.
   */
  async cleanupTestData(): Promise<void> {
    try {
      const teams = await this.getTeams();
      for (const team of teams) {
        // Get and cancel all invitations
        const invitations = await this.getInvitations(team.id);
        for (const invitation of invitations) {
          if (invitation.status === 'pending') {
            await this.cancelInvitation(team.id, invitation.id);
          }
        }
      }
    } catch (error) {
      console.warn('Cleanup failed:', error);
    }
  }
}

/**
 * Storage state file path for authenticated sessions.
 */
export const STORAGE_STATE = {
  owner: 'playwright/.auth/owner.json',
  admin: 'playwright/.auth/admin.json',
  member: 'playwright/.auth/member.json',
};

/**
 * Mock Stripe checkout for testing billing flows.
 * Returns a fake checkout URL that can be intercepted.
 */
export function getMockStripeCheckoutUrl(priceId: string): string {
  return `https://checkout.stripe.com/test?price=${priceId}`;
}

/**
 * Check if we're running in CI environment.
 */
export function isCI(): boolean {
  return !!process.env.CI;
}
