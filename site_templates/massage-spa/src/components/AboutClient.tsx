"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import type { Dictionary } from "@/lib/dictionaries";

interface AboutClientProps {
  dict: Dictionary;
}

export function AboutClient({ dict }: AboutClientProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, margin: "-100px" });

  return (
    <div
      ref={ref}
      className="grid md:grid-cols-2 gap-12 md:gap-16 items-center max-w-5xl mx-auto"
    >
      <motion.div
        initial={{ opacity: 0, x: -40 }}
        animate={isInView ? { opacity: 1, x: 0 } : {}}
        transition={{ duration: 0.6 }}
        className="relative order-2 md:order-1"
      >
        <div className="relative aspect-[3/4] max-w-sm mx-auto">
          <div className="absolute -inset-4 border-2 border-sage/30 rounded-3xl" />
          <div className="absolute -inset-2 bg-terracotta/10 rounded-3xl" />

          <video
            src="/daiane-video.mp4"
            autoPlay
            loop
            muted
            playsInline
            className="relative w-full h-full object-cover rounded-2xl shadow-medium"
          />

          <div className="absolute -bottom-6 -right-6 w-24 h-24 bg-sage/20 rounded-full blur-2xl" />
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, x: 40 }}
        animate={isInView ? { opacity: 1, x: 0 } : {}}
        transition={{ duration: 0.6, delay: 0.2 }}
        className="order-1 md:order-2"
      >
        <span className="text-sage font-sans text-sm tracking-widest uppercase mb-4 block">
          {dict.about.title}
        </span>

        <h2 className="font-serif text-3xl md:text-4xl text-foreground mb-6">
          {dict.about.greeting}
        </h2>

        <div className="w-12 h-0.5 bg-terracotta mb-6" />

        <p className="font-sans text-lg text-foreground/80 leading-relaxed">
          {dict.about.description}
        </p>

        <div className="mt-8 pl-6 border-l-2 border-sage/40">
          <p className="font-serif text-xl italic text-foreground/70">
            "{dict.about.quote}"
          </p>
        </div>
      </motion.div>
    </div>
  );
}
