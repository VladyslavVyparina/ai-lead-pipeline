import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { LocationClient } from "./LocationClient";

interface LocationSectionProps {
  lang: Locale;
  dict: Dictionary;
}

export function LocationSection({ lang, dict }: LocationSectionProps) {
  return (
    <section id="location" className="section-padding bg-background">
      <div className="container mx-auto">
        <div className="max-w-6xl mx-auto">
          <LocationClient lang={lang} dict={dict} />
        </div>
      </div>
    </section>
  );
}
