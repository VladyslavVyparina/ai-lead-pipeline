"use client";

import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import { Sparkles, Leaf, Heart } from "lucide-react";
import type { Dictionary } from "@/lib/dictionaries";

interface ServiceItem {
  name: string;
  price: string;
}

interface PricingClientProps {
  dict: Dictionary;
}

export function PricingClient({ dict }: PricingClientProps) {
  const ref = useRef(null);
  const isInView = useInView(ref, { once: true, amount: 0.2 });

  const lead = (dict as { lead?: { services?: ServiceItem[] } }).lead;
  const leadServices = lead?.services ?? [];

  const massageServices: ServiceItem[] = [
    { name: dict.services.relaxante, price: "€ 25,00" },
    { name: dict.services.geotermica, price: "€ 25,00" },
    { name: dict.services.indiana, price: "€ 25,00" },
    { name: dict.services.facial, price: "€ 25,00" },
    { name: dict.services.modeladora, price: "€ 30,00" },
  ];

  const treatmentServices: ServiceItem[] = [
    { name: dict.services.drenagem, price: "€ 25,00" },
    { name: dict.services.shiatsu, price: "€ 25,00" },
    { name: dict.services.reflexologia, price: "€ 25,00" },
    { name: dict.services.miofascial, price: "€ 25,00" },
  ];

  const comboServices: ServiceItem[] = [
    { name: dict.services.relaxanteMiofascial, price: "€ 38,00" },
    { name: dict.services.relaxanteEscaldapes, price: "€ 38,00" },
    { name: dict.services.drenagemModeladora, price: "€ 43,00" },
  ];

  // Lead preview: split the injected services across up to three columns so
  // the grid stays balanced, replacing Kaapora's own fixed menu.
  const leadColumns: ServiceItem[][] = [[], [], []];
  leadServices.forEach((svc, i) => leadColumns[i % 3].push(svc));

  const containerVariants = {
    hidden: { opacity: 0 },
    visible: {
      opacity: 1,
      transition: {
        staggerChildren: 0.1,
      },
    },
  };

  const itemVariants = {
    hidden: { opacity: 0, y: 20 },
    visible: {
      opacity: 1,
      y: 0,
      transition: { duration: 0.5 },
    },
  };

  const ServiceCard = ({
    title,
    services,
    icon: Icon,
    subtitle,
  }: {
    title: string;
    services: ServiceItem[];
    icon: React.ElementType;
    subtitle?: string;
  }) => (
    <div className="glass-card-hover p-6 md:p-8">
      {title && (
        <div className="flex items-center gap-3 mb-6">
          <div className="w-10 h-10 rounded-full bg-sage/20 flex items-center justify-center">
            <Icon className="text-sage" size={20} />
          </div>
          <div>
            <h3 className="font-serif text-xl text-foreground">{title}</h3>
            {subtitle && (
              <span className="text-sm text-muted-foreground">{subtitle}</span>
            )}
          </div>
        </div>
      )}

      <div className="space-y-4">
        {services.map((service, index) => (
          <div
            key={index}
            className="flex items-center justify-between py-2 border-b border-border/50 last:border-0"
          >
            <span className="font-sans text-foreground/80">{service.name}</span>
            <span className="font-sans font-medium text-foreground">
              {service.price}
            </span>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <div ref={ref}>
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={isInView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.6 }}
        className="text-center mb-12"
      >
        <span className="text-sage font-sans text-sm tracking-widest uppercase mb-4 block">
          {dict.nav.services}
        </span>
        <h2 className="font-serif text-3xl md:text-4xl text-foreground mb-4">
          {dict.pricing.title}
        </h2>
        <p className="font-sans text-lg text-muted-foreground">
          {dict.pricing.subtitle}
        </p>
      </motion.div>

      {/* Promotional Banner — Kaapora-specific, hidden in lead previews */}
      {!lead && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={isInView ? { opacity: 1, y: 0 } : {}}
          transition={{ duration: 0.6, delay: 0.2 }}
          className="mb-12"
        >
          <div className="glass-card p-6 md:p-8 text-center border-2 border-terracotta/30 bg-gradient-to-r from-terracotta/5 to-sage/5">
            <div className="inline-block px-4 py-1 bg-terracotta text-white rounded-full text-sm font-sans font-medium mb-3">
              {dict.pricing.promo.badge}
            </div>
            <p className="font-serif text-xl md:text-2xl text-foreground mb-2">
              {dict.pricing.promo.text}
            </p>
            <p className="font-sans text-muted-foreground">
              {dict.pricing.promo.cta}
            </p>
          </div>
        </motion.div>
      )}

      {lead ? (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          {leadColumns
            .filter((column) => column.length > 0)
            .map((column, index) => (
              <ServiceCard
                key={index}
                title=""
                services={column}
                icon={[Sparkles, Heart, Leaf][index] ?? Sparkles}
              />
            ))}
        </div>
      ) : (
        <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-6">
          <ServiceCard
            title={dict.pricing.massage}
            services={massageServices}
            icon={Sparkles}
          />
          <ServiceCard
            title={dict.pricing.treatments}
            services={treatmentServices}
            icon={Heart}
          />
          <ServiceCard
            title={dict.pricing.combos}
            services={comboServices}
            icon={Leaf}
            subtitle={dict.pricing.minutes}
          />
        </div>
      )}

      <motion.p
        initial={{ opacity: 0 }}
        animate={isInView ? { opacity: 1 } : {}}
        transition={{ delay: 0.6 }}
        className="text-center text-sm text-muted-foreground mt-8 italic"
      >
        {dict.pricing.disclaimer}
      </motion.p>
    </div>
  );
}
