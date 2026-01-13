"use client";

import * as React from "react";
import { ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";

const faqs = [
  {
    question: "How does the 14-day free trial work?",
    answer:
      "You get full access to all features on your selected plan for 14 days, no credit card required. At the end of the trial, you can choose to subscribe or downgrade to our free plan.",
  },
  {
    question: "Can I change my plan later?",
    answer:
      "Absolutely! You can upgrade or downgrade your plan at any time. When upgrading, you'll be prorated for the remainder of your billing cycle. When downgrading, the change takes effect at your next billing date.",
  },
  {
    question: "What payment methods do you accept?",
    answer:
      "We accept all major credit cards (Visa, MasterCard, American Express), PayPal, and bank transfers for annual enterprise plans. All payments are processed securely through Stripe.",
  },
  {
    question: "Is my data secure?",
    answer:
      "Security is our top priority. We're SOC 2 Type II certified, use AES-256 encryption at rest, TLS 1.3 in transit, and offer features like SSO, 2FA, and audit logs. Your data is stored in ISO 27001 certified data centers.",
  },
  {
    question: "Do you offer custom enterprise solutions?",
    answer:
      "Yes! Our Enterprise plan can be customized to fit your specific needs, including custom integrations, dedicated support, SLA guarantees, and flexible billing options. Contact our sales team to learn more.",
  },
  {
    question: "What kind of support do you offer?",
    answer:
      "Free plans get community support through our forums and documentation. Pro plans include priority email support with 24-hour response times. Enterprise plans get 24/7 phone support and a dedicated account manager.",
  },
  {
    question: "Can I cancel my subscription anytime?",
    answer:
      "Yes, you can cancel your subscription at any time from your account settings. You'll continue to have access until the end of your current billing period, and you can always export your data.",
  },
  {
    question: "Do you offer discounts for annual billing?",
    answer:
      "Yes! When you choose annual billing, you get 2 months free (approximately 17% off). This applies to both Pro and Enterprise plans.",
  },
];

export function FAQ() {
  const [openIndex, setOpenIndex] = React.useState<number | null>(null);

  return (
    <section id="faq" className="bg-muted/50 py-20 md:py-32">
      <div className="container">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="mb-4 text-3xl font-bold tracking-tight md:text-4xl">
            Frequently Asked Questions
          </h2>
          <p className="text-lg text-muted-foreground">
            Everything you need to know about SaaSify. Can&apos;t find the answer
            you&apos;re looking for? Contact our support team.
          </p>
        </div>

        <div className="mx-auto max-w-3xl">
          <div className="divide-y rounded-lg border bg-background">
            {faqs.map((faq, index) => (
              <div key={index}>
                <button
                  className="flex w-full items-center justify-between px-6 py-4 text-left"
                  onClick={() => setOpenIndex(openIndex === index ? null : index)}
                  aria-expanded={openIndex === index}
                >
                  <span className="font-medium">{faq.question}</span>
                  <ChevronDown
                    className={cn(
                      "h-5 w-5 shrink-0 text-muted-foreground transition-transform duration-200",
                      openIndex === index && "rotate-180"
                    )}
                  />
                </button>
                <div
                  className={cn(
                    "grid transition-all duration-200",
                    openIndex === index
                      ? "grid-rows-[1fr] opacity-100"
                      : "grid-rows-[0fr] opacity-0"
                  )}
                >
                  <div className="overflow-hidden">
                    <p className="px-6 pb-4 text-muted-foreground">
                      {faq.answer}
                    </p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
