import type { Metadata } from "next";
import { getDictionary } from "@/lib/dictionaries";
import type { Locale } from "@/i18n-config";
import { Navbar } from "@/components/Navbar";
import { HeroSection } from "@/components/HeroSection";
import { AboutSection } from "@/components/AboutSection";
import { PricingSection } from "@/components/PricingSection";
import { LocationSection } from "@/components/LocationSection";
import { Footer } from "@/components/Footer";
import { StickyCTA } from "@/components/StickyCTA";
import { SchemaLD } from "@/components/SchemaLD";
import { businessInfo } from "@/lib/business";
import { siteConfig } from "@/lib/site-config";
import { getLeadOverlay } from "@/lib/preview-config";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ lang: Locale }>;
}): Promise<Metadata> {
  const { lang } = await params;
  const dict = await getDictionary(lang);

  return {
    title: dict.meta.home.title,
    description: dict.meta.home.description,
    alternates: {
      canonical: `/${lang}`,
      languages: {
        "pt-PT": "/pt",
        "en-US": "/en",
      },
    },
  };
}

export default async function HomePage({
  params,
}: {
  params: Promise<{ lang: Locale }>;
}) {
  const { lang } = await params;
  const dict = await getDictionary(lang);
  const lead = getLeadOverlay();

  const localBusinessSchema = {
    "@context": "https://schema.org",
    "@type": "HealthAndBeautyBusiness",
    name: businessInfo.name,
    description: businessInfo.description[lang],
    url: `${siteConfig.canonicalBaseUrl}/${lang}`,
    telephone: businessInfo.contact.phone,
    address: {
      "@type": "PostalAddress",
      streetAddress: businessInfo.address.streetAddress,
      addressLocality: businessInfo.address.addressLocality,
      addressRegion: businessInfo.address.addressRegion,
      postalCode: businessInfo.address.postalCode,
      addressCountry: businessInfo.address.addressCountry,
    },
    geo: {
      "@type": "GeoCoordinates",
      latitude: businessInfo.geo.latitude,
      longitude: businessInfo.geo.longitude,
    },
    openingHoursSpecification: [
      {
        "@type": "OpeningHoursSpecification",
        dayOfWeek: ["Monday", "Tuesday", "Thursday", "Friday"],
        opens: "15:00",
        closes: "20:00",
      },
      {
        "@type": "OpeningHoursSpecification",
        dayOfWeek: "Sunday",
        opens: "10:00",
        closes: "18:00",
      },
    ],
    priceRange: businessInfo.priceRange,
    sameAs: businessInfo.sameAs,
  };

  return (
    <>
      {/* Don't emit LocalBusiness structured data for an unofficial preview. */}
      {!lead && <SchemaLD schema={localBusinessSchema} />}
      <div className="min-h-screen bg-background">
        <Navbar lang={lang} dict={dict} />
        <main>
          <HeroSection lang={lang} dict={dict} />
          {/* About uses Kaapora's therapist media — omit for lead previews. */}
          {!lead && <AboutSection lang={lang} dict={dict} />}
          <PricingSection lang={lang} dict={dict} />
          <LocationSection lang={lang} dict={dict} />
        </main>
        <Footer lang={lang} dict={dict} />
        <StickyCTA lang={lang} dict={dict} />
      </div>
    </>
  );
}
