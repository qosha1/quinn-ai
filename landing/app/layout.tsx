import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";
import { ThemeProvider } from "@/components/theme-provider";
import { Header } from "@/components/header";
import { Footer } from "@/components/footer";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: {
    default: "SaaSify - Modern B2B SaaS Platform",
    template: "%s | SaaSify",
  },
  description:
    "The modern platform for building and scaling your B2B SaaS business. Start free, scale globally.",
  keywords: [
    "SaaS",
    "B2B",
    "platform",
    "business",
    "software",
    "cloud",
    "enterprise",
  ],
  authors: [{ name: "SaaSify" }],
  creator: "SaaSify",
  openGraph: {
    type: "website",
    locale: "en_US",
    url: "https://saasify.com",
    title: "SaaSify - Modern B2B SaaS Platform",
    description:
      "The modern platform for building and scaling your B2B SaaS business.",
    siteName: "SaaSify",
  },
  twitter: {
    card: "summary_large_image",
    title: "SaaSify - Modern B2B SaaS Platform",
    description:
      "The modern platform for building and scaling your B2B SaaS business.",
    creator: "@saasify",
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  metadataBase: new URL("https://saasify.com"),
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    name: "SaaSify",
    applicationCategory: "BusinessApplication",
    operatingSystem: "Web",
    description:
      "The modern platform for building and scaling your B2B SaaS business.",
    offers: {
      "@type": "AggregateOffer",
      priceCurrency: "USD",
      lowPrice: "0",
      highPrice: "99",
    },
  };

  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }}
        />
      </head>
      <body className={inter.className}>
        <ThemeProvider
          attribute="class"
          defaultTheme="system"
          enableSystem
          disableTransitionOnChange
        >
          <div className="relative flex min-h-screen flex-col">
            <Header />
            <main className="flex-1">{children}</main>
            <Footer />
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
