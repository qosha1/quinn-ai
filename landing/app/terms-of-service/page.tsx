import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Terms of Service",
  description: "Read the terms and conditions for using SaaSify services.",
};

export default function TermsOfServicePage() {
  return (
    <div className="py-16 md:py-24">
      <div className="container">
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-8 text-4xl font-bold tracking-tight">
            Terms of Service
          </h1>
          <p className="mb-8 text-muted-foreground">
            Last updated: January 1, 2025
          </p>

          <div className="prose prose-slate dark:prose-invert max-w-none">
            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                1. Acceptance of Terms
              </h2>
              <p className="mb-4 text-muted-foreground">
                By accessing or using SaaSify (&quot;the Service&quot;), you agree to be
                bound by these Terms of Service. If you do not agree to these
                terms, do not use the Service.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                2. Description of Service
              </h2>
              <p className="mb-4 text-muted-foreground">
                SaaSify provides a platform for building and scaling B2B SaaS
                applications, including but not limited to:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Application hosting and infrastructure</li>
                <li>User authentication and management</li>
                <li>Billing and subscription management</li>
                <li>Analytics and reporting tools</li>
                <li>API access and integrations</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                3. Account Registration
              </h2>
              <p className="mb-4 text-muted-foreground">
                To use the Service, you must:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Be at least 18 years old</li>
                <li>Provide accurate and complete information</li>
                <li>Maintain the security of your account credentials</li>
                <li>Notify us immediately of any unauthorized access</li>
                <li>Accept responsibility for all activities under your account</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                4. Subscription and Billing
              </h2>
              <p className="mb-4 text-muted-foreground">
                Paid features are billed in advance on a monthly or annual basis.
                By subscribing, you authorize us to charge your payment method.
                Subscriptions automatically renew unless cancelled before the
                renewal date.
              </p>
              <p className="mb-4 text-muted-foreground">
                Refunds are handled on a case-by-case basis. Contact support for
                refund requests within 14 days of purchase.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">5. Acceptable Use</h2>
              <p className="mb-4 text-muted-foreground">You agree not to:</p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Violate any applicable laws or regulations</li>
                <li>Infringe on intellectual property rights</li>
                <li>Transmit malware or malicious code</li>
                <li>Attempt to gain unauthorized access</li>
                <li>Interfere with the Service&apos;s operation</li>
                <li>Use the Service for illegal or harmful activities</li>
                <li>Resell or redistribute the Service without permission</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                6. Intellectual Property
              </h2>
              <p className="mb-4 text-muted-foreground">
                The Service and its original content, features, and functionality
                are owned by SaaSify and are protected by international
                copyright, trademark, and other intellectual property laws.
              </p>
              <p className="mb-4 text-muted-foreground">
                You retain ownership of any content you create using the Service.
                By using the Service, you grant us a license to host and display
                your content as necessary to provide the Service.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">7. Data and Privacy</h2>
              <p className="mb-4 text-muted-foreground">
                Our collection and use of personal information is governed by our
                Privacy Policy. By using the Service, you consent to our data
                practices as described in the Privacy Policy.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                8. Service Availability
              </h2>
              <p className="mb-4 text-muted-foreground">
                We strive to maintain 99.9% uptime but do not guarantee
                uninterrupted access. We may modify, suspend, or discontinue the
                Service at any time with reasonable notice.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                9. Limitation of Liability
              </h2>
              <p className="mb-4 text-muted-foreground">
                TO THE MAXIMUM EXTENT PERMITTED BY LAW, SAASIFY SHALL NOT BE
                LIABLE FOR ANY INDIRECT, INCIDENTAL, SPECIAL, CONSEQUENTIAL, OR
                PUNITIVE DAMAGES, OR ANY LOSS OF PROFITS OR REVENUES.
              </p>
              <p className="mb-4 text-muted-foreground">
                Our total liability shall not exceed the amount you paid us in
                the twelve months preceding the claim.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                10. Indemnification
              </h2>
              <p className="mb-4 text-muted-foreground">
                You agree to indemnify and hold harmless SaaSify from any claims,
                damages, or expenses arising from your use of the Service or
                violation of these Terms.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">11. Termination</h2>
              <p className="mb-4 text-muted-foreground">
                We may terminate or suspend your account at any time for
                violation of these Terms. Upon termination, your right to use the
                Service ceases immediately. You may export your data before
                termination.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                12. Changes to Terms
              </h2>
              <p className="mb-4 text-muted-foreground">
                We reserve the right to modify these Terms at any time. We will
                provide notice of significant changes. Continued use of the
                Service after changes constitutes acceptance of the new Terms.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                13. Governing Law
              </h2>
              <p className="mb-4 text-muted-foreground">
                These Terms are governed by the laws of the State of California,
                without regard to its conflict of law provisions. Any disputes
                shall be resolved in the courts of San Francisco County,
                California.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">14. Contact</h2>
              <p className="mb-4 text-muted-foreground">
                For questions about these Terms, contact us at:
              </p>
              <p className="text-muted-foreground">
                Email: legal@saasify.com
                <br />
                Address: 123 SaaS Street, San Francisco, CA 94102
              </p>
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
