export const siteConfig = {
  name: "Kaapora",
  businessName: "Kaapora Massagem Terapêutica",
  canonicalBaseUrl: process.env.NEXT_PUBLIC_SITE_URL || "https://kaapora.pt",
  defaultLocale: "pt" as const,
  locales: ["pt", "en"] as const,

  social: {
    instagram: "https://www.instagram.com/kaapora_kaapora/",
    whatsapp: "https://wa.me/351911150331",
  },

  openGraph: {
    type: "website" as const,
    siteName: "Kaapora Massagem Terapêutica",
    images: [
      {
        url: "/og-image.jpg",
        width: 1200,
        height: 630,
        alt: "Kaapora - Massagem Terapêutica no Porto",
      },
    ],
  } as const,

  twitter: {
    card: "summary_large_image",
  },
} as const;

export type Locale = (typeof siteConfig.locales)[number];
