"use client";

import { motion } from "framer-motion";
import { ChevronDown } from "lucide-react";
import type { Dictionary } from "@/lib/dictionaries";

interface HeroClientProps {
  dict: Dictionary;
}

export function HeroClient({ dict }: HeroClientProps) {
  const scrollToServices = () => {
    const element = document.getElementById("services");
    if (element) {
      element.scrollIntoView({ behavior: "smooth" });
    }
  };

  return (
    <div className="relative z-10 container mx-auto px-4 md:px-8 text-center">
      <motion.div
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, delay: 0.2 }}
        className="max-w-3xl mx-auto"
      >
        <motion.div
          initial={{ scaleX: 0 }}
          animate={{ scaleX: 1 }}
          transition={{ duration: 0.6, delay: 0.4 }}
          className="w-16 h-0.5 bg-sage mx-auto mb-8"
        />

        <h1 className="font-serif text-4xl md:text-5xl lg:text-6xl text-foreground leading-tight mb-6">
          {dict.hero.headline}
        </h1>

        <p className="font-sans text-lg md:text-xl text-foreground/80 leading-relaxed mb-10 max-w-2xl mx-auto">
          {dict.hero.subheadline}
        </p>

        <motion.button
          onClick={scrollToServices}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          className="btn-primary text-base px-8 py-4"
        >
          {dict.hero.cta}
        </motion.button>
      </motion.div>

      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.2 }}
        className="absolute bottom-8 left-1/2 -translate-x-1/2"
      >
        <motion.div
          animate={{ y: [0, 8, 0] }}
          transition={{ duration: 1.5, repeat: Infinity }}
        >
          <ChevronDown className="text-foreground/50" size={32} />
        </motion.div>
      </motion.div>
    </div>
  );
}
