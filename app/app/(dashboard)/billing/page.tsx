"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { billingApi, Subscription, Usage } from "@/lib/api";
import { redirectToPortal } from "@/lib/stripe";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  CreditCard,
  ArrowRight,
  FileText,
  Zap,
  ExternalLink,
  Loader2,
} from "lucide-react";
import { formatDate, formatCurrency } from "@/lib/utils";

export default function BillingPage() {
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [usage, setUsage] = useState<Usage | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPortalLoading, setIsPortalLoading] = useState(false);

  useEffect(() => {
    async function fetchBillingData() {
      try {
        const [subResponse, usageResponse] = await Promise.all([
          billingApi.getSubscription(),
          billingApi.getUsage(),
        ]);
        setSubscription(subResponse.data);
        setUsage(usageResponse.data);
      } catch (error) {
        console.error("Failed to fetch billing data:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchBillingData();
  }, []);

  const handleManageBilling = async () => {
    setIsPortalLoading(true);
    try {
      await redirectToPortal();
    } catch (error) {
      console.error("Failed to open billing portal:", error);
      setIsPortalLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "active":
        return <Badge variant="success">Active</Badge>;
      case "trialing":
        return <Badge variant="warning">Trial</Badge>;
      case "past_due":
        return <Badge variant="destructive">Past Due</Badge>;
      case "canceled":
        return <Badge variant="secondary">Canceled</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getUsagePercentage = (used: number, limit: number) => {
    return Math.min(100, Math.round((used / limit) * 100));
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Billing</h1>
          <p className="text-muted-foreground">Loading billing information...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Billing</h1>
          <p className="text-muted-foreground">
            Manage your subscription and billing settings
          </p>
        </div>
        <Button onClick={handleManageBilling} disabled={isPortalLoading}>
          {isPortalLoading ? (
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          ) : (
            <ExternalLink className="mr-2 h-4 w-4" />
          )}
          Manage Billing
        </Button>
      </div>

      {/* Current Plan */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Current Plan</CardTitle>
              <CardDescription>
                Your current subscription details
              </CardDescription>
            </div>
            {subscription && getStatusBadge(subscription.status)}
          </div>
        </CardHeader>
        <CardContent>
          {subscription ? (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <p className="text-2xl font-bold">
                    {subscription.plan.name}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    {formatCurrency(subscription.plan.price_monthly)} / month
                  </p>
                </div>
                <Button variant="outline" asChild>
                  <Link href="/billing/plans">
                    Change Plan
                    <ArrowRight className="ml-2 h-4 w-4" />
                  </Link>
                </Button>
              </div>
              <div className="text-sm text-muted-foreground">
                <p>
                  Current period:{" "}
                  {formatDate(subscription.current_period_start)} -{" "}
                  {formatDate(subscription.current_period_end)}
                </p>
                {subscription.cancel_at_period_end && (
                  <p className="text-destructive mt-1">
                    Your subscription will be canceled at the end of the current
                    billing period.
                  </p>
                )}
              </div>
            </div>
          ) : (
            <div className="text-center py-8">
              <p className="text-muted-foreground mb-4">
                You don&apos;t have an active subscription.
              </p>
              <Button asChild>
                <Link href="/billing/plans">View Plans</Link>
              </Button>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Usage Stats */}
      {usage && (
        <Card>
          <CardHeader>
            <CardTitle>Usage</CardTitle>
            <CardDescription>
              Your current usage for this billing period
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* Members */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Team Members</span>
                <span className="text-sm text-muted-foreground">
                  {usage.members.used} / {usage.members.limit}
                </span>
              </div>
              <div className="h-2 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all"
                  style={{
                    width: `${getUsagePercentage(
                      usage.members.used,
                      usage.members.limit
                    )}%`,
                  }}
                />
              </div>
            </div>

            {/* Storage */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">Storage</span>
                <span className="text-sm text-muted-foreground">
                  {usage.storage.used} GB / {usage.storage.limit} GB
                </span>
              </div>
              <div className="h-2 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all"
                  style={{
                    width: `${getUsagePercentage(
                      usage.storage.used,
                      usage.storage.limit
                    )}%`,
                  }}
                />
              </div>
            </div>

            {/* API Calls */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <span className="text-sm font-medium">API Calls</span>
                <span className="text-sm text-muted-foreground">
                  {usage.api_calls.used.toLocaleString()} /{" "}
                  {usage.api_calls.limit.toLocaleString()}
                </span>
              </div>
              <div className="h-2 bg-secondary rounded-full overflow-hidden">
                <div
                  className="h-full bg-primary transition-all"
                  style={{
                    width: `${getUsagePercentage(
                      usage.api_calls.used,
                      usage.api_calls.limit
                    )}%`,
                  }}
                />
              </div>
            </div>
          </CardContent>
          <CardFooter>
            <p className="text-xs text-muted-foreground">
              Usage resets at the start of each billing period.
            </p>
          </CardFooter>
        </Card>
      )}

      {/* Quick Links */}
      <div className="grid gap-4 md:grid-cols-3">
        <Link href="/billing/plans">
          <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <Zap className="h-5 w-5" />
                  Plans
                </span>
                <ArrowRight className="h-4 w-4" />
              </CardTitle>
              <CardDescription>
                Compare plans and upgrade your subscription
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Link href="/billing/invoices">
          <Card className="hover:bg-muted/50 transition-colors cursor-pointer">
            <CardHeader>
              <CardTitle className="flex items-center justify-between text-base">
                <span className="flex items-center gap-2">
                  <FileText className="h-5 w-5" />
                  Invoices
                </span>
                <ArrowRight className="h-4 w-4" />
              </CardTitle>
              <CardDescription>
                View and download past invoices
              </CardDescription>
            </CardHeader>
          </Card>
        </Link>

        <Card
          className="hover:bg-muted/50 transition-colors cursor-pointer"
          onClick={handleManageBilling}
        >
          <CardHeader>
            <CardTitle className="flex items-center justify-between text-base">
              <span className="flex items-center gap-2">
                <CreditCard className="h-5 w-5" />
                Payment Method
              </span>
              <ExternalLink className="h-4 w-4" />
            </CardTitle>
            <CardDescription>
              Update your payment method in Stripe
            </CardDescription>
          </CardHeader>
        </Card>
      </div>
    </div>
  );
}
