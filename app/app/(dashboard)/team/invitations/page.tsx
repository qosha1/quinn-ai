"use client";

import { useEffect, useState } from "react";
import { teamApi, TeamInvitation } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Mail, MoreHorizontal, RefreshCw, X, Loader2, Plus } from "lucide-react";
import { formatDate } from "@/lib/utils";

export default function TeamInvitationsPage() {
  const [invitations, setInvitations] = useState<TeamInvitation[]>([]);
  const [teamId, setTeamId] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [showInviteDialog, setShowInviteDialog] = useState(false);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRole, setInviteRole] = useState<"admin" | "member">("member");
  const [isInviting, setIsInviting] = useState(false);
  const [inviteError, setInviteError] = useState<string | null>(null);

  useEffect(() => {
    async function fetchInvitations() {
      try {
        const teamsResponse = await teamApi.getTeams();
        if (teamsResponse.data.length > 0) {
          const currentTeamId = teamsResponse.data[0].id;
          setTeamId(currentTeamId);

          const invitationsResponse = await teamApi.getInvitations(
            currentTeamId
          );
          setInvitations(invitationsResponse.data);
        }
      } catch (error) {
        console.error("Failed to fetch invitations:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchInvitations();
  }, []);

  const handleSendInvite = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!teamId) return;

    setIsInviting(true);
    setInviteError(null);

    try {
      const response = await teamApi.createInvitation(
        teamId,
        inviteEmail,
        inviteRole
      );
      setInvitations((prev) => [...prev, response.data]);
      setShowInviteDialog(false);
      setInviteEmail("");
      setInviteRole("member");
    } catch (error) {
      setInviteError("Failed to send invitation. Please try again.");
      console.error("Failed to send invitation:", error);
    } finally {
      setIsInviting(false);
    }
  };

  const handleResendInvite = async (invitationId: string) => {
    if (!teamId) return;

    try {
      await teamApi.resendInvitation(teamId, invitationId);
    } catch (error) {
      console.error("Failed to resend invitation:", error);
    }
  };

  const handleCancelInvite = async (invitationId: string) => {
    if (!teamId) return;

    try {
      await teamApi.cancelInvitation(teamId, invitationId);
      setInvitations((prev) => prev.filter((i) => i.id !== invitationId));
    } catch (error) {
      console.error("Failed to cancel invitation:", error);
    }
  };

  const getStatusBadgeVariant = (status: string) => {
    switch (status) {
      case "pending":
        return "warning";
      case "accepted":
        return "success";
      case "expired":
        return "secondary";
      default:
        return "outline";
    }
  };

  const pendingInvitations = invitations.filter((i) => i.status === "pending");

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Invitations</h1>
          <p className="text-muted-foreground">Loading invitations...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Invitations</h1>
          <p className="text-muted-foreground">
            Invite new members to join your team
          </p>
        </div>
        <Dialog open={showInviteDialog} onOpenChange={setShowInviteDialog}>
          <DialogTrigger asChild>
            <Button>
              <Plus className="mr-2 h-4 w-4" />
              Invite Member
            </Button>
          </DialogTrigger>
          <DialogContent>
            <form onSubmit={handleSendInvite}>
              <DialogHeader>
                <DialogTitle>Invite Team Member</DialogTitle>
                <DialogDescription>
                  Send an invitation to join your team. They will receive an
                  email with a link to accept.
                </DialogDescription>
              </DialogHeader>
              <div className="space-y-4 py-4">
                {inviteError && (
                  <div className="p-3 text-sm text-destructive bg-destructive/10 rounded-md">
                    {inviteError}
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor="email">Email address</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="colleague@example.com"
                    value={inviteEmail}
                    onChange={(e) => setInviteEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label>Role</Label>
                  <div className="flex gap-2">
                    <Button
                      type="button"
                      variant={inviteRole === "member" ? "default" : "outline"}
                      className="flex-1"
                      onClick={() => setInviteRole("member")}
                    >
                      Member
                    </Button>
                    <Button
                      type="button"
                      variant={inviteRole === "admin" ? "default" : "outline"}
                      className="flex-1"
                      onClick={() => setInviteRole("admin")}
                    >
                      Admin
                    </Button>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {inviteRole === "admin"
                      ? "Admins can manage team members and settings"
                      : "Members can access team resources"}
                  </p>
                </div>
              </div>
              <DialogFooter>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => setShowInviteDialog(false)}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={isInviting}>
                  {isInviting && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  <Mail className="mr-2 h-4 w-4" />
                  Send Invitation
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </div>

      {/* Pending Invitations */}
      <Card>
        <CardHeader>
          <CardTitle>Pending Invitations ({pendingInvitations.length})</CardTitle>
          <CardDescription>
            Invitations that are waiting to be accepted
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Invited</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead className="w-[70px]"></TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {pendingInvitations.map((invitation) => (
                <TableRow key={invitation.id}>
                  <TableCell className="font-medium">
                    {invitation.email}
                  </TableCell>
                  <TableCell>
                    <Badge variant="outline">{invitation.role}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={getStatusBadgeVariant(invitation.status)}>
                      {invitation.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(invitation.invited_at)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {formatDate(invitation.expires_at)}
                  </TableCell>
                  <TableCell>
                    <DropdownMenu>
                      <DropdownMenuTrigger asChild>
                        <Button variant="ghost" size="icon">
                          <MoreHorizontal className="h-4 w-4" />
                        </Button>
                      </DropdownMenuTrigger>
                      <DropdownMenuContent align="end">
                        <DropdownMenuItem
                          onClick={() => handleResendInvite(invitation.id)}
                        >
                          <RefreshCw className="mr-2 h-4 w-4" />
                          Resend Invitation
                        </DropdownMenuItem>
                        <DropdownMenuItem
                          className="text-destructive focus:text-destructive"
                          onClick={() => handleCancelInvite(invitation.id)}
                        >
                          <X className="mr-2 h-4 w-4" />
                          Cancel Invitation
                        </DropdownMenuItem>
                      </DropdownMenuContent>
                    </DropdownMenu>
                  </TableCell>
                </TableRow>
              ))}
              {pendingInvitations.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-8">
                    <p className="text-muted-foreground">
                      No pending invitations. Invite a new team member!
                    </p>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      {/* All Invitations History */}
      {invitations.length > pendingInvitations.length && (
        <Card>
          <CardHeader>
            <CardTitle>Invitation History</CardTitle>
            <CardDescription>
              All past invitations including accepted and expired
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Email</TableHead>
                  <TableHead>Role</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Invited</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invitations
                  .filter((i) => i.status !== "pending")
                  .map((invitation) => (
                    <TableRow key={invitation.id}>
                      <TableCell className="font-medium">
                        {invitation.email}
                      </TableCell>
                      <TableCell>
                        <Badge variant="outline">{invitation.role}</Badge>
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={getStatusBadgeVariant(invitation.status)}
                        >
                          {invitation.status}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-muted-foreground">
                        {formatDate(invitation.invited_at)}
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
