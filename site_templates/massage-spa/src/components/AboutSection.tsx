import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { AboutClient } from "./AboutClient";

interface AboutSectionProps {
  lang: Locale;
  dict: Dictionary;
}

export function AboutSection({ lang, dict }: AboutSectionProps) {
  return (
    <section id="about" className="section-padding bg-background">
      <div className="container mx-auto">
        <AboutClient dict={dict} />
      </div>
    </section>
  );
}
