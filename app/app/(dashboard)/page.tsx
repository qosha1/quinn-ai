"use client";

import { useAuthStore } from "@/stores/auth-store";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Users, CreditCard, Activity, TrendingUp } from "lucide-react";

const stats = [
  {
    title: "Total Members",
    value: "12",
    description: "+2 from last month",
    icon: Users,
  },
  {
    title: "Current Plan",
    value: "Pro",
    description: "Renews Jan 15, 2025",
    icon: CreditCard,
  },
  {
    title: "API Calls",
    value: "45.2K",
    description: "23% of monthly limit",
    icon: Activity,
  },
  {
    title: "Storage Used",
    value: "8.2 GB",
    description: "41% of 20 GB limit",
    icon: TrendingUp,
  },
];

export default function DashboardPage() {
  const { user } = useAuthStore();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Welcome back, {user?.first_name || "User"}! Here&apos;s an overview of
          your account.
        </p>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.title}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">
                {stat.title}
              </CardTitle>
              <stat.icon className="h-4 w-4 text-muted-foreground" />
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground">
                {stat.description}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Recent Activity */}
      <Card>
        <CardHeader>
          <CardTitle>Recent Activity</CardTitle>
          <CardDescription>
            Your team&apos;s latest actions and updates
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[
              {
                action: "New member invited",
                user: "john@example.com",
                time: "2 hours ago",
              },
              {
                action: "API key created",
                user: "Production API",
                time: "5 hours ago",
              },
              {
                action: "Subscription upgraded",
                user: "Pro Plan",
                time: "1 day ago",
              },
              {
                action: "Team settings updated",
                user: "Billing address",
                time: "2 days ago",
              },
            ].map((activity, i) => (
              <div
                key={i}
                className="flex items-center justify-between border-b pb-4 last:border-0 last:pb-0"
              >
                <div>
                  <p className="text-sm font-medium">{activity.action}</p>
                  <p className="text-sm text-muted-foreground">
                    {activity.user}
                  </p>
                </div>
                <span className="text-xs text-muted-foreground">
                  {activity.time}
                </span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
