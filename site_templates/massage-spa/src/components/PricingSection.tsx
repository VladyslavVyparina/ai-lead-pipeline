import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { PricingClient } from "./PricingClient";

interface PricingSectionProps {
  lang: Locale;
  dict: Dictionary;
}

export function PricingSection({ lang, dict }: PricingSectionProps) {
  return (
    <section id="services" className="section-padding bg-secondary/30">
      <div className="container mx-auto">
        <div className="max-w-5xl mx-auto">
          <PricingClient dict={dict} />
        </div>
      </div>
    </section>
  );
}
