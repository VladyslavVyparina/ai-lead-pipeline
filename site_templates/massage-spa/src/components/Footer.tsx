import { Instagram, MessageCircle } from "lucide-react";
import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { siteConfig } from "@/lib/site-config";
import { businessInfo } from "@/lib/business";

interface FooterProps {
  lang: Locale;
  dict: Dictionary;
}

export function Footer({ lang, dict }: FooterProps) {
  const whatsappLink = `${
    businessInfo.contact.whatsapp
  }?text=${encodeURIComponent(businessInfo.contact.whatsappMessage[lang])}`;

  return (
    <footer className="bg-deep-earth text-warm-sand py-12">
      <div className="container mx-auto px-4 md:px-8">
        <div className="max-w-5xl mx-auto">
          <div className="flex flex-col md:flex-row items-center justify-between gap-8">
            <div className="text-center md:text-left">
              <span className="font-serif text-2xl tracking-[0.2em]">
                {dict.footer.businessName.toUpperCase()}
              </span>
              <p
                className="font-sans text-sm mt-2"
                style={{ color: "hsl(30 20% 55%)" }}
              >
                {dict.footer.tagline}
              </p>
            </div>

            <div className="flex items-center gap-6">
              <span
                className="font-sans text-sm"
                style={{ color: "hsl(30 20% 55%)" }}
              >
                {dict.footer.followUs}
              </span>
              <div className="flex items-center gap-4">
                <a
                  href={siteConfig.social.instagram}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-10 h-10 rounded-full bg-warm-sand/10 flex items-center justify-center hover:bg-warm-sand/20 transition-colors"
                  aria-label="Instagram"
                >
                  <Instagram size={20} />
                </a>
                <a
                  href={whatsappLink}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-10 h-10 rounded-full bg-warm-sand/10 flex items-center justify-center hover:bg-warm-sand/20 transition-colors"
                  aria-label="WhatsApp"
                >
                  <MessageCircle size={20} />
                </a>
              </div>
            </div>
          </div>

          <div className="w-full h-px bg-warm-sand/10 my-8" />

          <p
            className="font-sans text-sm text-center"
            style={{ color: "hsl(30 20% 40%)" }}
          >
            {dict.footer.copyright}
          </p>
        </div>
      </div>
    </footer>
  );
}
