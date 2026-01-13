import Link from "next/link";
import { Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

const plans = [
  {
    name: "Free",
    description: "Perfect for trying out the platform",
    price: "$0",
    period: "forever",
    features: [
      "Up to 3 team members",
      "1,000 API requests/month",
      "Basic analytics",
      "Community support",
      "1 project",
    ],
    cta: "Get Started",
    href: "/signup?plan=free",
    popular: false,
  },
  {
    name: "Pro",
    description: "Best for growing businesses",
    price: "$29",
    period: "/month",
    features: [
      "Up to 20 team members",
      "100,000 API requests/month",
      "Advanced analytics",
      "Priority email support",
      "Unlimited projects",
      "Custom integrations",
      "SSO authentication",
    ],
    cta: "Start Free Trial",
    href: "/signup?plan=pro",
    popular: true,
  },
  {
    name: "Enterprise",
    description: "For large-scale operations",
    price: "$99",
    period: "/month",
    features: [
      "Unlimited team members",
      "Unlimited API requests",
      "Custom analytics",
      "24/7 phone support",
      "Unlimited projects",
      "Custom integrations",
      "SSO + SAML",
      "Dedicated account manager",
      "SLA guarantee",
      "Custom contracts",
    ],
    cta: "Contact Sales",
    href: "/contact",
    popular: false,
  },
];

export function Pricing() {
  return (
    <section id="pricing" className="bg-muted/50 py-20 md:py-32">
      <div className="container">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Simple, Transparent Pricing
          </h2>
          <p className="text-lg text-muted-foreground">
            Choose the plan that fits your business. All plans include a 14-day
            free trial.
          </p>
        </div>

        <div className="mx-auto grid max-w-5xl gap-8 lg:grid-cols-3">
          {plans.map((plan) => (
            <Card
              key={plan.name}
              className={cn(
                "relative flex flex-col",
                plan.popular && "border-primary shadow-lg"
              )}
            >
              {plan.popular && (
                <Badge className="absolute -top-3 left-1/2 -translate-x-1/2">
                  Most Popular
                </Badge>
              )}
              <CardHeader>
                <CardTitle>{plan.name}</CardTitle>
                <CardDescription>{plan.description}</CardDescription>
                <div className="mt-4">
                  <span className="text-4xl font-bold">{plan.price}</span>
                  <span className="text-muted-foreground">{plan.period}</span>
                </div>
              </CardHeader>
              <CardContent className="flex-1">
                <ul className="space-y-3">
                  {plan.features.map((feature) => (
                    <li key={feature} className="flex items-start gap-2">
                      <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                      <span className="text-sm">{feature}</span>
                    </li>
                  ))}
                </ul>
              </CardContent>
              <CardFooter>
                <Button
                  className="w-full"
                  variant={plan.popular ? "default" : "outline"}
                  asChild
                >
                  <Link href={plan.href}>{plan.cta}</Link>
                </Button>
              </CardFooter>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
