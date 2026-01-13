import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Privacy Policy",
  description: "Learn how SaaSify collects, uses, and protects your personal information.",
};

export default function PrivacyPolicyPage() {
  return (
    <div className="py-16 md:py-24">
      <div className="container">
        <div className="mx-auto max-w-3xl">
          <h1 className="mb-8 text-4xl font-bold tracking-tight">
            Privacy Policy
          </h1>
          <p className="mb-8 text-muted-foreground">
            Last updated: January 1, 2025
          </p>

          <div className="prose prose-slate dark:prose-invert max-w-none">
            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">1. Introduction</h2>
              <p className="mb-4 text-muted-foreground">
                SaaSify (&quot;we,&quot; &quot;our,&quot; or &quot;us&quot;) is committed to protecting your
                privacy. This Privacy Policy explains how we collect, use,
                disclose, and safeguard your information when you use our
                platform.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                2. Information We Collect
              </h2>
              <p className="mb-4 text-muted-foreground">
                We collect information you provide directly to us, including:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Account information (name, email, password)</li>
                <li>Profile information (company name, job title)</li>
                <li>Payment information (processed securely via Stripe)</li>
                <li>Communications you send to us</li>
                <li>Usage data and analytics</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                3. How We Use Your Information
              </h2>
              <p className="mb-4 text-muted-foreground">
                We use the information we collect to:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Provide, maintain, and improve our services</li>
                <li>Process transactions and send related information</li>
                <li>Send technical notices and support messages</li>
                <li>Respond to your comments and questions</li>
                <li>Analyze usage patterns and trends</li>
                <li>Protect against fraudulent or illegal activity</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                4. Information Sharing
              </h2>
              <p className="mb-4 text-muted-foreground">
                We do not sell your personal information. We may share your
                information with:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Service providers who assist in our operations</li>
                <li>Professional advisors (lawyers, accountants)</li>
                <li>Law enforcement when required by law</li>
                <li>Other parties with your consent</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">5. Data Security</h2>
              <p className="mb-4 text-muted-foreground">
                We implement appropriate technical and organizational measures to
                protect your personal information, including:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>AES-256 encryption at rest</li>
                <li>TLS 1.3 encryption in transit</li>
                <li>Regular security audits and penetration testing</li>
                <li>SOC 2 Type II compliance</li>
                <li>Access controls and authentication</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                6. Data Retention
              </h2>
              <p className="mb-4 text-muted-foreground">
                We retain your personal information for as long as your account
                is active or as needed to provide you services. You can request
                deletion of your data at any time by contacting us.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">7. Your Rights</h2>
              <p className="mb-4 text-muted-foreground">
                Depending on your location, you may have the right to:
              </p>
              <ul className="mb-4 list-disc pl-6 text-muted-foreground">
                <li>Access your personal information</li>
                <li>Correct inaccurate data</li>
                <li>Delete your data</li>
                <li>Object to processing</li>
                <li>Data portability</li>
                <li>Withdraw consent</li>
              </ul>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                8. Cookies and Tracking
              </h2>
              <p className="mb-4 text-muted-foreground">
                We use cookies and similar tracking technologies to collect
                information about your browsing activities. You can control
                cookies through your browser settings.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                9. International Transfers
              </h2>
              <p className="mb-4 text-muted-foreground">
                Your information may be transferred to and processed in countries
                other than your own. We ensure appropriate safeguards are in
                place for such transfers.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">
                10. Changes to This Policy
              </h2>
              <p className="mb-4 text-muted-foreground">
                We may update this Privacy Policy from time to time. We will
                notify you of any changes by posting the new policy on this page
                and updating the &quot;Last updated&quot; date.
              </p>
            </section>

            <section className="mb-8">
              <h2 className="mb-4 text-2xl font-semibold">11. Contact Us</h2>
              <p className="mb-4 text-muted-foreground">
                If you have any questions about this Privacy Policy, please
                contact us at:
              </p>
              <p className="text-muted-foreground">
                Email: privacy@saasify.com
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
