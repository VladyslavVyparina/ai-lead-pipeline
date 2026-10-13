import "server-only";
import type { Locale } from "@/i18n-config";
import { getLeadOverlay, type LeadOverlay } from "@/lib/preview-config";

const dictionaries = {
  pt: () => import("../../messages/pt.json").then((module) => module.default),
  en: () => import("../../messages/en.json").then((module) => module.default),
};

export const getDictionary = async (locale: Locale) => {
  const base = await dictionaries[locale]();
  const lead = getLeadOverlay();
  if (!lead) {
    return base as typeof base & { lead: LeadOverlay | null };
  }
  // Lead preview: overlay the injected lead data onto Kaapora's copy. Static
  // labels/structure stay; dynamic hero/meta strings and the `lead` namespace
  // (read by client components) come from the pipeline's SITE_CONFIG.
  return {
    ...base,
    hero: {
      ...base.hero,
      headline: lead.hero.headline,
      subheadline: lead.hero.subheadline,
      cta: lead.hero.cta,
    },
    meta: {
      ...base.meta,
      home: {
        title: lead.seoTitle,
        description: lead.seoDescription,
      },
    },
    lead,
  } as typeof base & { lead: LeadOverlay | null };
};

export type Dictionary = Awaited<ReturnType<typeof getDictionary>>;
