import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "QuinnAI Board",
  description: "QuinnAI org management board",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
