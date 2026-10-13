"use client";

import { useState, useEffect } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Menu, X, MessageCircle } from "lucide-react";
import Link from "next/link";
import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { businessInfo } from "@/lib/business";

interface NavbarClientProps {
  lang: Locale;
  dict: Dictionary;
}

export function NavbarClient({ lang, dict }: NavbarClientProps) {
  const [isScrolled, setIsScrolled] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => {
      setIsScrolled(window.scrollY > 20);
    };
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const scrollToSection = (id: string) => {
    const element = document.getElementById(id);
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
    }
    setIsMobileMenuOpen(false);
  };

  const lead = (dict as {
    lead?: { businessName: string; contact: { whatsappUrl: string } };
  }).lead;
  const whatsappLink =
    lead?.contact.whatsappUrl ||
    `${businessInfo.contact.whatsapp}?text=${encodeURIComponent(
      businessInfo.contact.whatsappMessage[lang]
    )}`;
  const brandLabel = lead?.businessName || "KAAPORA";

  return (
    <motion.nav
      initial={{ y: -100 }}
      animate={{ y: 0 }}
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        isScrolled
          ? "bg-background/80 backdrop-blur-lg shadow-soft"
          : "bg-transparent"
      }`}
    >
      <div className="container mx-auto px-4 md:px-8">
        <div className="flex items-center justify-between h-20">
          <Link
            href={`/${lang}`}
            className={`font-serif text-foreground hover:text-terracotta-dark transition-colors whitespace-nowrap truncate max-w-[60vw] md:max-w-none ${
              lead ? "text-lg md:text-xl tracking-[0.06em]" : "text-2xl tracking-[0.2em]"
            }`}
          >
            {brandLabel}
          </Link>

          <div className="hidden md:flex items-center gap-8">
            <button
              onClick={() => scrollToSection("about")}
              className="text-foreground/80 hover:text-foreground transition-colors font-sans text-sm tracking-wide"
            >
              {dict.nav.about}
            </button>
            <button
              onClick={() => scrollToSection("services")}
              className="text-foreground/80 hover:text-foreground transition-colors font-sans text-sm tracking-wide"
            >
              {dict.nav.services}
            </button>
            <button
              onClick={() => scrollToSection("location")}
              className="text-foreground/80 hover:text-foreground transition-colors font-sans text-sm tracking-wide"
            >
              {dict.nav.location}
            </button>
          </div>

          <div className="hidden md:flex items-center gap-4">
            <div className="flex items-center bg-secondary/50 rounded-full p-1">
              <Link
                href={`/pt`}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  lang === "pt"
                    ? "bg-terracotta text-deep-earth"
                    : "text-foreground/60 hover:text-foreground"
                }`}
              >
                PT
              </Link>
              <Link
                href={`/en`}
                className={`px-3 py-1.5 rounded-full text-sm font-medium transition-all ${
                  lang === "en"
                    ? "bg-terracotta text-deep-earth"
                    : "text-foreground/60 hover:text-foreground"
                }`}
              >
                EN
              </Link>
            </div>

            <a
              href={whatsappLink}
              target="_blank"
              rel="noopener noreferrer"
              className="btn-primary flex items-center gap-2 text-sm"
            >
              <MessageCircle size={18} />
              {dict.nav.book}
            </a>
          </div>

          <button
            onClick={() => setIsMobileMenuOpen(!isMobileMenuOpen)}
            className="md:hidden p-2 text-foreground"
          >
            {isMobileMenuOpen ? <X size={24} /> : <Menu size={24} />}
          </button>
        </div>
      </div>

      <AnimatePresence>
        {isMobileMenuOpen && (
          <motion.div
            initial={{ opacity: 0, height: 0 }}
            animate={{ opacity: 1, height: "auto" }}
            exit={{ opacity: 0, height: 0 }}
            className="md:hidden bg-background/95 backdrop-blur-lg border-t border-border"
          >
            <div className="container mx-auto px-4 py-6 flex flex-col gap-4">
              <button
                onClick={() => scrollToSection("about")}
                className="text-foreground/80 hover:text-foreground transition-colors font-sans py-2 text-left"
              >
                {dict.nav.about}
              </button>
              <button
                onClick={() => scrollToSection("services")}
                className="text-foreground/80 hover:text-foreground transition-colors font-sans py-2 text-left"
              >
                {dict.nav.services}
              </button>
              <button
                onClick={() => scrollToSection("location")}
                className="text-foreground/80 hover:text-foreground transition-colors font-sans py-2 text-left"
              >
                {dict.nav.location}
              </button>

              <div className="flex items-center gap-2 py-2">
                <Link
                  href={`/pt`}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                    lang === "pt"
                      ? "bg-terracotta text-deep-earth"
                      : "bg-secondary text-foreground/60"
                  }`}
                >
                  PT
                </Link>
                <Link
                  href={`/en`}
                  className={`px-4 py-2 rounded-full text-sm font-medium transition-all ${
                    lang === "en"
                      ? "bg-terracotta text-deep-earth"
                      : "bg-secondary text-foreground/60"
                  }`}
                >
                  EN
                </Link>
              </div>

              <a
                href={whatsappLink}
                target="_blank"
                rel="noopener noreferrer"
                className="btn-primary flex items-center justify-center gap-2 mt-2"
              >
                <MessageCircle size={18} />
                {dict.nav.book}
              </a>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.nav>
  );
}
