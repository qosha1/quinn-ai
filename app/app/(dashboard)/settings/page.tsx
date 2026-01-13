"use client";

import Link from "next/link";
import {
  Card,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { User, Shield, Key, ArrowRight } from "lucide-react";

const settingsLinks = [
  {
    title: "Profile",
    description: "Update your personal information and avatar",
    href: "/settings/profile",
    icon: User,
  },
  {
    title: "Security",
    description: "Manage your password and two-factor authentication",
    href: "/settings/security",
    icon: Shield,
  },
  {
    title: "API Keys",
    description: "Create and manage API keys for integrations",
    href: "/settings/api-keys",
    icon: Key,
  },
];

export default function SettingsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Settings</h1>
        <p className="text-muted-foreground">
          Manage your account settings and preferences
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
        {settingsLinks.map((link) => (
          <Link key={link.href} href={link.href}>
            <Card className="hover:bg-muted/50 transition-colors cursor-pointer h-full">
              <CardHeader>
                <CardTitle className="flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <link.icon className="h-5 w-5" />
                    {link.title}
                  </span>
                  <ArrowRight className="h-4 w-4" />
                </CardTitle>
                <CardDescription>{link.description}</CardDescription>
              </CardHeader>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}
