"use client";

import { useState, useEffect } from "react";
import { MessageCircle, Phone } from "lucide-react";
import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { businessInfo } from "@/lib/business";

interface StickyCTAProps {
  lang: Locale;
  dict: Dictionary;
}

export function StickyCTA({ lang, dict }: StickyCTAProps) {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsVisible(window.scrollY > 300);
    };

    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const lead = (dict as {
    lead?: { contact: { phone: string; whatsappUrl: string } };
  }).lead;
  const whatsappLink =
    lead?.contact.whatsappUrl ||
    `${businessInfo.contact.whatsapp}?text=${encodeURIComponent(
      businessInfo.contact.whatsappMessage[lang]
    )}`;
  const phone = lead?.contact.phone || businessInfo.contact.phone;

  if (!isVisible) return null;

  return (
    <div className="md:hidden fixed bottom-0 left-0 right-0 z-40 bg-background/95 backdrop-blur-lg border-t border-border shadow-medium">
      <div className="container mx-auto px-4 py-3 flex items-center gap-3">
        <a
          href={whatsappLink}
          target="_blank"
          rel="noopener noreferrer"
          className="flex-1 btn-primary flex items-center justify-center gap-2 py-3"
        >
          <MessageCircle size={18} />
          {dict.sticky.book}
        </a>
        <a
          href={`tel:${phone}`}
          className="btn-outline flex items-center justify-center gap-2 py-3 px-6"
        >
          <Phone size={18} />
          {dict.sticky.call}
        </a>
      </div>
    </div>
  );
}
