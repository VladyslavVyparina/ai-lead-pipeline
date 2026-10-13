import { Inter, Playfair_Display } from "next/font/google";
import type { Metadata } from "next";
import { i18n, type Locale } from "@/i18n-config";
import { siteConfig } from "@/lib/site-config";
import { getDictionary } from "@/lib/dictionaries";
import { getLeadOverlay } from "@/lib/preview-config";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-inter",
  display: "swap",
});

const playfair = Playfair_Display({
  subsets: ["latin"],
  variable: "--font-playfair",
  display: "swap",
});

export async function generateStaticParams() {
  return i18n.locales.map((locale) => ({ lang: locale }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: Locale }>;
}): Promise<Metadata> {
  const { lang } = await params;
  const dict = await getDictionary(lang);
  const lead = getLeadOverlay();

  return {
    title: {
      default: dict.meta.home.title,
      template: `%s | ${lead ? lead.businessName : siteConfig.businessName}`,
    },
    description: dict.meta.home.description,
    // Lead previews are unlisted, labelled concepts — never index them.
    ...(lead?.noindex ? { robots: { index: false, follow: false } } : {}),
    icons: {
      icon: [
        { url: "/favicon.ico", sizes: "32x32" },
        { url: "/favicon.svg", type: "image/svg+xml" },
        { url: "/favicon-96x96.png", sizes: "96x96", type: "image/png" },
      ],
      apple: "/apple-touch-icon.png",
    },
    openGraph: {
      type: "website",
      siteName: siteConfig.openGraph.siteName,
      locale: lang === "pt" ? "pt_PT" : "en_US",
      images: [
        {
          url: `${siteConfig.canonicalBaseUrl}/og-image.jpg`,
          width: 1200,
          height: 630,
          alt: "Kaapora - Massagem Terapêutica no Porto",
        },
      ],
    },
    twitter: {
      card: "summary_large_image",
      title: dict.meta.home.title,
      description: dict.meta.home.description,
      images: [`${siteConfig.canonicalBaseUrl}/og-image.jpg`],
    },
    manifest: "/site.webmanifest",
    alternates: {
      canonical: `/${lang}`,
      languages: {
        "pt-PT": "/pt",
        "en-US": "/en",
      },
    },
  };
}

export default async function LangLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ lang: Locale }>;
}) {
  const { lang } = await params;
  const lead = getLeadOverlay();

  // Recolor Kaapora's hsl(var(--token)) design system with the lead's own
  // brand palette when a preview injects one.
  const brandVars =
    lead && (lead.brand.primaryHsl || lead.brand.accentHsl)
      ? `:root{${lead.brand.primaryHsl ? `--terracotta:${lead.brand.primaryHsl};--primary:${lead.brand.primaryHsl};--ring:${lead.brand.primaryHsl};` : ""}${lead.brand.accentHsl ? `--sage:${lead.brand.accentHsl};--accent:${lead.brand.accentHsl};` : ""}}`
      : "";

  // A preview must read as complete instantly — no scroll-gated reveals. Force
  // framer-motion's entrance state (inline opacity/transform) to the settled
  // values so nothing depends on the IntersectionObserver firing. Only applied
  // in preview mode, so the live Kaapora site keeps its animations.
  const staticReveal = lead
    ? `[style*="opacity"]{opacity:1 !important;}[style*="transform"]{transform:none !important;}`
    : "";
  const brandStyle = brandVars + staticReveal;

  return (
    <html
      lang={lang}
      className={`${inter.variable} ${playfair.variable}`}
      suppressHydrationWarning
    >
      <head>
        <link rel="preconnect" href="https://maps.googleapis.com" />
        <link rel="dns-prefetch" href="https://maps.googleapis.com" />
        {brandStyle ? <style dangerouslySetInnerHTML={{ __html: brandStyle }} /> : null}
      </head>
      <body
        className="min-h-screen bg-background text-foreground font-sans antialiased"
        suppressHydrationWarning
      >
        {lead?.preview ? (
          <div className="w-full bg-deep-earth text-cream text-center text-xs md:text-sm py-2 px-4">
            {lead.disclaimer}
          </div>
        ) : null}
        {children}
      </body>
    </html>
  );
}
