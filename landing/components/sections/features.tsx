import {
  BarChart3,
  Globe,
  Lock,
  Rocket,
  Users,
  Zap,
} from "lucide-react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const features = [
  {
    icon: Rocket,
    title: "Launch in Minutes",
    description:
      "Get your SaaS product up and running with our pre-built templates and one-click deployments.",
  },
  {
    icon: Users,
    title: "Team Management",
    description:
      "Built-in team invitations, roles, and permissions. Scale from solo to enterprise seamlessly.",
  },
  {
    icon: BarChart3,
    title: "Analytics Dashboard",
    description:
      "Real-time insights into your business metrics, user behavior, and revenue trends.",
  },
  {
    icon: Lock,
    title: "Enterprise Security",
    description:
      "SOC 2 compliant with SSO, 2FA, and audit logs. Your data is always protected.",
  },
  {
    icon: Globe,
    title: "Global Scale",
    description:
      "Deploy to any region with our global edge network. Sub-50ms latency worldwide.",
  },
  {
    icon: Zap,
    title: "API First",
    description:
      "Comprehensive REST and GraphQL APIs. Integrate with any tool in your stack.",
  },
];

export function Features() {
  return (
    <section id="features" className="py-20 md:py-32">
      <div className="container">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Everything You Need to Succeed
          </h2>
          <p className="text-lg text-muted-foreground">
            A complete toolkit for building and scaling your SaaS business. No
            compromises, no limitations.
          </p>
        </div>

        <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
          {features.map((feature) => (
            <Card key={feature.title} className="relative overflow-hidden">
              <CardHeader>
                <div className="mb-2 flex h-12 w-12 items-center justify-center rounded-lg bg-primary/10">
                  <feature.icon className="h-6 w-6 text-primary" />
                </div>
                <CardTitle>{feature.title}</CardTitle>
                <CardDescription>{feature.description}</CardDescription>
              </CardHeader>
              <CardContent>
                <div className="absolute -bottom-4 -right-4 h-24 w-24 rounded-full bg-primary/5" />
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    </section>
  );
}
