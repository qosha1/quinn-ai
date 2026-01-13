import Link from "next/link";
import { ArrowRight, CheckCircle2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const highlights = [
  "No credit card required",
  "14-day free trial",
  "Cancel anytime",
];

export function Hero() {
  return (
    <section className="relative overflow-hidden py-20 md:py-32">
      <div className="absolute inset-0 -z-10 bg-[radial-gradient(45%_40%_at_50%_60%,hsl(var(--primary)/0.1),transparent)]" />
      <div className="container">
        <div className="mx-auto max-w-3xl text-center">
          <Badge variant="secondary" className="mb-4">
            Announcing our Series A funding
          </Badge>
          <h1 className="mb-6 text-4xl font-bold tracking-tight md:text-6xl">
            Build Your SaaS Business{" "}
            <span className="text-primary">Faster Than Ever</span>
          </h1>
          <p className="mb-8 text-lg text-muted-foreground md:text-xl">
            The complete platform for building, launching, and scaling your B2B
            SaaS product. From idea to revenue in weeks, not months.
          </p>
          <div className="mb-8 flex flex-col gap-4 sm:flex-row sm:justify-center">
            <Button size="lg" asChild>
              <Link href="/signup">
                Start Free Trial
                <ArrowRight className="ml-2 h-4 w-4" />
              </Link>
            </Button>
            <Button size="lg" variant="outline" asChild>
              <Link href="#features">See How It Works</Link>
            </Button>
          </div>
          <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-muted-foreground">
            {highlights.map((highlight) => (
              <div key={highlight} className="flex items-center gap-2">
                <CheckCircle2 className="h-4 w-4 text-primary" />
                <span>{highlight}</span>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-16 flex justify-center">
          <div className="relative w-full max-w-4xl overflow-hidden rounded-xl border bg-muted/50 shadow-2xl">
            <div className="flex items-center gap-2 border-b bg-muted px-4 py-3">
              <div className="h-3 w-3 rounded-full bg-red-500" />
              <div className="h-3 w-3 rounded-full bg-yellow-500" />
              <div className="h-3 w-3 rounded-full bg-green-500" />
              <span className="ml-2 text-xs text-muted-foreground">
                dashboard.saasify.com
              </span>
            </div>
            <div className="aspect-[16/9] bg-gradient-to-br from-primary/5 to-primary/10 p-8">
              <div className="grid h-full gap-4 md:grid-cols-3">
                <div className="rounded-lg bg-background/80 p-4 shadow-sm">
                  <div className="mb-2 h-3 w-16 rounded bg-muted" />
                  <div className="h-8 w-24 rounded bg-primary/20" />
                </div>
                <div className="rounded-lg bg-background/80 p-4 shadow-sm">
                  <div className="mb-2 h-3 w-20 rounded bg-muted" />
                  <div className="h-8 w-28 rounded bg-primary/20" />
                </div>
                <div className="rounded-lg bg-background/80 p-4 shadow-sm">
                  <div className="mb-2 h-3 w-14 rounded bg-muted" />
                  <div className="h-8 w-20 rounded bg-primary/20" />
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
