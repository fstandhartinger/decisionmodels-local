import type { Metadata } from "next";
import type { ReactNode } from "react";
import { SiteFooter, SiteHeader } from "@/components/site-chrome";
import "./globals.css";

export const metadata: Metadata = {
  metadataBase: new URL("https://decisionmodels.io"),
  title: { default: "Run locally — Decision Models", template: "%s — Decision Models" },
  description: "Run open-weight decision models on hardware you control.",
  openGraph: {
    title: "Run locally — Decision Models",
    description: "Hardware guidance and a Jev-compatible local model installer.",
    images: ["/local/static/brand/og.png"],
    type: "website"
  },
  icons: { icon: "/local/static/brand/dm-glyph-mono-ink.svg" }
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <SiteHeader />
        <main id="main-content">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
