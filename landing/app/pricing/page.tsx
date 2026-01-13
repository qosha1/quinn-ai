import type { Metadata } from "next";
import { Pricing } from "@/components/sections/pricing";
import { FAQ } from "@/components/sections/faq";
import { CTA } from "@/components/sections/cta";

export const metadata: Metadata = {
  title: "Pricing",
  description:
    "Simple, transparent pricing for teams of all sizes. Start free and scale as you grow.",
};

export default function PricingPage() {
  return (
    <>
      <div className="py-12 md:py-16">
        <div className="container">
          <div className="mx-auto max-w-2xl text-center">
            <h1 className="mb-4 text-4xl font-bold tracking-tight md:text-5xl">
              Pricing Plans
            </h1>
            <p className="text-lg text-muted-foreground">
              Choose the perfect plan for your business. All plans include a
              14-day free trial with no credit card required.
            </p>
          </div>
        </div>
      </div>
      <Pricing />
      <FAQ />
      <CTA />
    </>
  );
}
