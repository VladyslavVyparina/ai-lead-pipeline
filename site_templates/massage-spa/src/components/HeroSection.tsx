import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { HeroClient } from "./HeroClient";
import { getLeadOverlay } from "@/lib/preview-config";
import Image from "next/image";

interface HeroSectionProps {
  lang: Locale;
  dict: Dictionary;
}

export function HeroSection({ lang, dict }: HeroSectionProps) {
  const lead = getLeadOverlay();
  const heroImage = lead?.brand.hero || "/hero-spa.jpg";
  const heroAlt = lead?.businessName || "Kaapora Spa Interior";

  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden">
      <div className="absolute inset-0">
        {/* Remote lead images are unoptimized to avoid next/image domain config. */}
        <Image
          src={heroImage}
          alt={heroAlt}
          fill
          priority
          unoptimized={heroImage.startsWith("http")}
          className="object-cover"
          sizes="100vw"
        />
        <div className="absolute inset-0 bg-gradient-to-b from-background/40 via-background/30 to-background/80" />
      </div>
      <HeroClient dict={dict} />
    </section>
  );
}
