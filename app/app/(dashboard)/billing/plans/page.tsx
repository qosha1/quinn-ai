"use client";

import { useEffect, useState } from "react";
import { billingApi, Plan, Subscription } from "@/lib/api";
import { redirectToCheckout } from "@/lib/stripe";
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
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Check, Loader2 } from "lucide-react";
import { formatCurrency } from "@/lib/utils";

export default function PlansPage() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [subscription, setSubscription] = useState<Subscription | null>(null);
  const [billingInterval, setBillingInterval] = useState<"month" | "year">(
    "month"
  );
  const [isLoading, setIsLoading] = useState(true);
  const [loadingPlanId, setLoadingPlanId] = useState<string | null>(null);

  useEffect(() => {
    async function fetchData() {
      try {
        const [plansResponse, subResponse] = await Promise.all([
          billingApi.getPlans(),
          billingApi.getSubscription().catch(() => null),
        ]);
        setPlans(plansResponse.data);
        if (subResponse) {
          setSubscription(subResponse.data);
        }
      } catch (error) {
        console.error("Failed to fetch plans:", error);
      } finally {
        setIsLoading(false);
      }
    }

    fetchData();
  }, []);

  const handleSelectPlan = async (planId: string) => {
    setLoadingPlanId(planId);
    try {
      await redirectToCheckout(planId, billingInterval);
    } catch (error) {
      console.error("Failed to start checkout:", error);
      setLoadingPlanId(null);
    }
  };

  const getPrice = (plan: Plan) => {
    return billingInterval === "month"
      ? plan.price_monthly
      : plan.price_yearly;
  };

  const isCurrentPlan = (plan: Plan) => {
    return subscription?.plan.id === plan.id;
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Plans</h1>
          <p className="text-muted-foreground">Loading available plans...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center">
        <h1 className="text-3xl font-bold tracking-tight">Choose Your Plan</h1>
        <p className="text-muted-foreground mt-2">
          Select the plan that best fits your needs. All plans include a 14-day
          free trial.
        </p>
      </div>

      {/* Billing Toggle */}
      <div className="flex justify-center">
        <Tabs
          value={billingInterval}
          onValueChange={(v) => setBillingInterval(v as "month" | "year")}
        >
          <TabsList>
            <TabsTrigger value="month">Monthly</TabsTrigger>
            <TabsTrigger value="year">
              Yearly
              <Badge variant="secondary" className="ml-2">
                Save 20%
              </Badge>
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {/* Plans Grid */}
      <div className="grid gap-6 md:grid-cols-3">
        {plans.map((plan) => (
          <Card
            key={plan.id}
            className={
              plan.name === "Pro"
                ? "border-primary shadow-lg relative"
                : undefined
            }
          >
            {plan.name === "Pro" && (
              <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">
                Most Popular
              </Badge>
            )}
            <CardHeader>
              <CardTitle>{plan.name}</CardTitle>
              <CardDescription>{plan.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Price */}
              <div>
                <span className="text-4xl font-bold">
                  {formatCurrency(getPrice(plan))}
                </span>
                <span className="text-muted-foreground">
                  /{billingInterval === "month" ? "mo" : "yr"}
                </span>
                {billingInterval === "year" && (
                  <p className="text-sm text-muted-foreground mt-1">
                    {formatCurrency(plan.price_yearly / 12)}/month billed
                    annually
                  </p>
                )}
              </div>

              {/* Features */}
              <ul className="space-y-3">
                {plan.features.map((feature, i) => (
                  <li key={i} className="flex items-center gap-2">
                    <Check className="h-4 w-4 text-primary shrink-0" />
                    <span className="text-sm">{feature}</span>
                  </li>
                ))}
              </ul>

              {/* Limits */}
              <div className="space-y-2 pt-4 border-t">
                <p className="text-sm font-medium">Limits</p>
                <ul className="space-y-1 text-sm text-muted-foreground">
                  <li>{plan.limits.members} team members</li>
                  <li>{plan.limits.storage_gb} GB storage</li>
                  <li>{plan.limits.api_calls.toLocaleString()} API calls/mo</li>
                </ul>
              </div>
            </CardContent>
            <CardFooter>
              {isCurrentPlan(plan) ? (
                <Button className="w-full" variant="outline" disabled>
                  Current Plan
                </Button>
              ) : (
                <Button
                  className="w-full"
                  variant={plan.name === "Pro" ? "default" : "outline"}
                  onClick={() => handleSelectPlan(plan.id)}
                  disabled={loadingPlanId !== null}
                >
                  {loadingPlanId === plan.id && (
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  )}
                  {subscription ? "Switch to " : "Get Started with "}
                  {plan.name}
                </Button>
              )}
            </CardFooter>
          </Card>
        ))}
      </div>

      {/* FAQ / Additional Info */}
      <Card>
        <CardHeader>
          <CardTitle>Frequently Asked Questions</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="font-medium">Can I change plans later?</p>
            <p className="text-sm text-muted-foreground">
              Yes, you can upgrade or downgrade your plan at any time. Changes
              take effect immediately, and we&apos;ll prorate the difference.
            </p>
          </div>
          <div>
            <p className="font-medium">What happens when I exceed my limits?</p>
            <p className="text-sm text-muted-foreground">
              You&apos;ll receive a notification when you&apos;re approaching
              your limits. You can upgrade your plan or purchase additional
              capacity.
            </p>
          </div>
          <div>
            <p className="font-medium">How do I cancel my subscription?</p>
            <p className="text-sm text-muted-foreground">
              You can cancel your subscription at any time from the billing
              settings. You&apos;ll continue to have access until the end of
              your billing period.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
