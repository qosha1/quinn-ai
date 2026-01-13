"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { teamApi, Team, TeamMember } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar";
import { Users, Mail, Settings, ArrowRight } from "lucide-react";

export default function TeamPage() {
  const [team, setTeam] = useState<Team | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    async function fetchTeamData() {
      try {
        const teamsResponse = await teamApi.getTeams();
        if (teamsResponse.data.length > 0) {
          const currentTeam = teamsResponse.data[0];
          setTeam(currentTeam);

          const membersResponse = await teamApi.getMembers(currentTeam.id);
          setMembers(membersResponse.data);
        }
      } catch (error) {
        console.error("Failed to fetch team data:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchTeamData();
  }, []);

  const getInitials = (firstName?: string, lastName?: string) => {
    const first = firstName?.charAt(0) || "";
    const last = lastName?.charAt(0) || "";
    return (first + last).toUpperCase() || "U";
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Team</h1>
          <p className="text-muted-foreground">Loading team information...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Team</h1>
          <p className="text-muted-foreground">
            Manage your team members and settings
          </p>
        </div>
      </div>

      {/* Quick Stats */}
      <div className="grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Members</CardTitle>
            <Users className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{members.length}</div>
            <p className="text-xs text-muted-foreground">Active team members</p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Team Name</CardTitle>
            <Settings className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{team?.name || "My Team"}</div>
            <p className="text-xs text-muted-foreground">
              Slug: {team?.slug || "my-team"}
            </p>
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">
              Pending Invites
            </CardTitle>
            <Mail className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">2</div>
            <p className="text-xs text-muted-foreground">Awaiting response</p>
          </CardContent>
        </Card>
      </div>

      {/* Quick Links */}
      <div className="grid gap-4 md:grid-cols-3">
        <Link href="/team/members">
          <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  Members
                </span>
                <ArrowRight className="h-4 w-4" />
              </CardTitle>
              <CardDescription>
                View and manage team members, change roles
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/team/invitations">
          <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Mail className="h-5 w-5" />
                  Invitations
                </span>
                <ArrowRight className="h-4 w-4" />
              </CardTitle>
              <CardDescription>
                Send invites and manage pending invitations
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/team/settings">
          <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <Settings className="h-5 w-5" />
                  Settings
                </span>
                <ArrowRight className="h-4 w-4" />
              </CardTitle>
              <CardDescription>
                Update team name, billing, and preferences
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>
      </div>

      {/* Recent Members */}
      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <div>
            <CardTitle>Recent Members</CardTitle>
            <CardDescription>
              Your team&apos;s most recently joined members
            </CardDescription>
          </div>
          <Button variant="outline" asChild>
            <Link href="/team/members">View all</Link>
          </Button>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {members.slice(0, 5).map((member) => (
              <div
                key={member.id}
                className="flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <Avatar>
                    <AvatarImage src={member.user.avatar_url} />
                    <AvatarFallback>
                      {getInitials(
                        member.user.first_name,
                        member.user.last_name
                      )}
                    </AvatarFallback>
                  </Avatar>
                  <div>
                    <p className="text-sm font-medium">
                      {member.user.first_name} {member.user.last_name}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      {member.user.email}
                    </p>
                  </div>
                </div>
                <Badge
                  variant={
                    member.role === "owner"
                      ? "default"
                      : member.role === "admin"
                      ? "secondary"
                      : "outline"
                  }
                >
                  {member.role}
                </Badge>
              </div>
            ))}
            {members.length === 0 && (
              <p className="text-sm text-muted-foreground text-center py-4">
                No team members yet. Invite your first member!
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
