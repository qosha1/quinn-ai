"use client";

import { useEffect, useState } from "react";
import { teamApi, Team } from "@/lib/api";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Loader2, AlertTriangle } from "lucide-react";

export default function TeamSettingsPage() {
  const [team, setTeam] = useState<Team | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);
  const [deleteConfirmation, setDeleteConfirmation] = useState("");

  const [formData, setFormData] = useState({
    name: "",
  });

  useEffect(() => {
    async function fetchTeam() {
      try {
        const teamsResponse = await teamApi.getTeams();
        if (teamsResponse.data.length > 0) {
          const currentTeam = teamsResponse.data[0];
          setTeam(currentTeam);
          setFormData({ name: currentTeam.name });
        }
      } catch (error) {
        console.error("Failed to fetch team:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchTeam();
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!team) return;

    setIsSaving(true);
    try {
      const response = await teamApi.updateTeam(team.id, { name: formData.name });
      setTeam(response.data);
    } catch (error) {
      console.error("Failed to update team:", error);
    } finally {
      setIsSaving(false);
    }
  };

  const handleDeleteTeam = async () => {
    if (!team || deleteConfirmation !== team.name) return;

    setIsDeleting(true);
    try {
      await teamApi.deleteTeam(team.id);
      // Redirect to create new team or home
      window.location.href = "/";
    } catch (error) {
      console.error("Failed to delete team:", error);
      setIsDeleting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Team Settings</h1>
          <p className="text-muted-foreground">Loading team settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Team Settings</h1>
        <p className="text-muted-foreground">
          Manage your team&apos;s settings and preferences
        </p>
      </div>

      {/* General Settings */}
      <Card>
        <form onSubmit={handleSubmit}>
          <CardHeader>
            <CardTitle>General</CardTitle>
            <CardDescription>
              Update your team&apos;s basic information
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="name">Team Name</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) =>
                  setFormData((prev) => ({ ...prev, name: e.target.value }))
                }
                placeholder="My Team"
              />
              <p className="text-xs text-muted-foreground">
                This is how your team will be identified across the platform.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="slug">Team URL</Label>
              <div className="flex items-center gap-2">
                <span className="text-sm text-muted-foreground">
                  app.saasify.com/
                </span>
                <Input
                  id="slug"
                  value={team?.slug || ""}
                  disabled
                  className="max-w-[200px]"
                />
              </div>
              <p className="text-xs text-muted-foreground">
                The team URL is automatically generated and cannot be changed.
              </p>
            </div>
          </CardContent>
          <CardFooter>
            <Button type="submit" disabled={isSaving}>
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Changes
            </Button>
          </CardFooter>
        </form>
      </Card>

      {/* Danger Zone */}
      <Card className="border-destructive">
        <CardHeader>
          <CardTitle className="text-destructive">Danger Zone</CardTitle>
          <CardDescription>
            Irreversible and destructive actions
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex items-center justify-between p-4 border rounded-lg">
            <div>
              <p className="font-medium">Delete Team</p>
              <p className="text-sm text-muted-foreground">
                Permanently delete your team and all associated data. This
                action cannot be undone.
              </p>
            </div>
            <Button
              variant="destructive"
              onClick={() => setShowDeleteDialog(true)}
            >
              Delete Team
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Delete Confirmation Dialog */}
      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <AlertTriangle className="h-5 w-5 text-destructive" />
              Delete Team
            </DialogTitle>
            <DialogDescription>
              This action is permanent and cannot be undone. All team members
              will lose access, and all data will be deleted.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-4">
            <div className="p-4 bg-destructive/10 rounded-lg">
              <p className="text-sm font-medium">This will delete:</p>
              <ul className="text-sm text-muted-foreground mt-2 space-y-1">
                <li>All team members and their access</li>
                <li>All team settings and preferences</li>
                <li>All API keys associated with this team</li>
                <li>Your subscription (no refunds will be issued)</li>
              </ul>
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm">
                Type <span className="font-mono font-bold">{team?.name}</span>{" "}
                to confirm
              </Label>
              <Input
                id="confirm"
                value={deleteConfirmation}
                onChange={(e) => setDeleteConfirmation(e.target.value)}
                placeholder="Enter team name"
              />
            </div>
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowDeleteDialog(false);
                setDeleteConfirmation("");
              }}
            >
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={handleDeleteTeam}
              disabled={isDeleting || deleteConfirmation !== team?.name}
            >
              {isDeleting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Delete Team Permanently
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
