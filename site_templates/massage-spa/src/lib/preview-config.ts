/**
 * AI Lead Pipeline preview adapter.
 *
 * When this Kaapora template is deployed as a per-lead preview, the pipeline
 * injects a `SITE_CONFIG` env var (see backend app/core/schemas.py -> SiteConfig
 * and the ContentPack under `content`). Each lead gets its OWN deployment, so
 * the value is constant for the deployment's lifetime and is safe to read at
 * module load — no multi-tenant per-request concern.
 *
 * Everything here is server-only (reads process.env). Lead data is surfaced to
 * client components through the dictionary (`dict.lead`, passed as props),
 * never by importing this module into a client bundle. When SITE_CONFIG is
 * absent, getLeadOverlay() returns null and the real Kaapora site renders
 * unchanged.
 */

type Fact = { value?: string | null } | string | number | null | undefined;

interface RawSiteConfig {
  business_name?: Fact;
  category?: string;
  city?: string;
  address?: Fact;
  hours?: Fact;
  phone?: Fact;
  email?: Fact;
  whatsapp?: Fact;
  socials?: Record<string, string>;
  services?: Array<{ name?: Fact; price?: Fact; description?: string }>;
  description?: Fact;
  logo_url?: string;
  hero_image_url?: string;
  primary_color?: string;
  accent_color?: string;
  seo_title?: string;
  seo_description?: string;
  booking_url?: string;
  mode?: string;
  noindex?: boolean;
  disclaimer?: string;
  content?: {
    hero?: { headline?: string; subheadline?: string };
    cta?: { label?: string; supporting?: string };
    contact?: {
      phone?: string;
      email?: string;
      whatsapp?: string;
      address?: string;
      instagram?: string;
    };
    theme?: Record<string, string>;
    disclaimer?: string;
    seo_title?: string;
    seo_description?: string;
    services?: Array<{ name?: string; price?: string; description?: string }>;
  };
}

export interface LeadService {
  name: string;
  price: string;
  description?: string;
}

export interface LeadOverlay {
  preview: boolean;
  noindex: boolean;
  businessName: string;
  city: string;
  hero: { headline: string; subheadline: string; cta: string };
  description: string;
  services: LeadService[];
  contact: {
    phone: string;
    whatsappUrl: string;
    email: string;
    instagram: string;
  };
  address: string;
  hours: string;
  brand: {
    primary: string;
    accent: string;
    logo: string;
    hero: string;
    // "H S% L%" triplets for Kaapora's hsl(var(--token)) design system.
    primaryHsl: string;
    accentHsl: string;
  };
  bookingUrl: string;
  disclaimer: string;
  seoTitle: string;
  seoDescription: string;
}

function factValue(fact: Fact): string {
  if (fact === null || fact === undefined) return "";
  if (typeof fact === "string") return fact.trim();
  if (typeof fact === "number") return String(fact);
  return (fact.value ?? "").toString().trim();
}

function hexToHslTriplet(hex: string): string {
  const clean = (hex || "").replace("#", "");
  if (clean.length !== 6) return "";
  const r = parseInt(clean.slice(0, 2), 16) / 255;
  const g = parseInt(clean.slice(2, 4), 16) / 255;
  const b = parseInt(clean.slice(4, 6), 16) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === r) h = (g - b) / d + (g < b ? 6 : 0);
    else if (max === g) h = (b - r) / d + 2;
    else h = (r - g) / d + 4;
    h *= 60;
  }
  return `${Math.round(h)} ${Math.round(s * 100)}% ${Math.round(l * 100)}%`;
}

function toWhatsAppUrl(raw: string): string {
  if (!raw) return "";
  if (raw.startsWith("http")) return raw;
  const digits = raw.replace(/\D/g, "");
  return digits ? `https://wa.me/${digits}` : "";
}

let cached: LeadOverlay | null | undefined;

export function getLeadOverlay(): LeadOverlay | null {
  if (cached !== undefined) return cached;

  const raw = process.env.SITE_CONFIG;
  if (!raw) {
    cached = null;
    return cached;
  }

  let cfg: RawSiteConfig;
  try {
    cfg = JSON.parse(raw) as RawSiteConfig;
  } catch {
    cached = null;
    return cached;
  }

  const content = cfg.content ?? {};
  const theme = content.theme ?? {};

  const services: LeadService[] = (content.services ?? cfg.services ?? [])
    .map((item) => ({
      name: factValue(item.name),
      price: factValue(item.price),
      description: (item.description ?? "").toString(),
    }))
    .filter((item) => item.name);

  const phone = content.contact?.phone || factValue(cfg.phone);
  const whatsappRaw = content.contact?.whatsapp || factValue(cfg.whatsapp) || phone;
  const businessName = factValue(cfg.business_name) || "Preview";
  const heroSub =
    content.hero?.subheadline || factValue(cfg.description) || "";

  cached = {
    preview: (cfg.mode ?? "preview") === "preview",
    noindex: cfg.noindex !== false,
    businessName,
    city: cfg.city ?? "",
    hero: {
      headline: content.hero?.headline || businessName,
      subheadline: heroSub,
      cta: content.cta?.label || "Marcar sessão",
    },
    description: heroSub,
    services,
    contact: {
      phone,
      whatsappUrl: toWhatsAppUrl(whatsappRaw),
      email: content.contact?.email || factValue(cfg.email),
      instagram: content.contact?.instagram || (cfg.socials ?? {}).instagram || "",
    },
    address: content.contact?.address || factValue(cfg.address),
    hours: factValue(cfg.hours),
    brand: {
      primary: theme.primary_color || cfg.primary_color || "",
      accent: theme.accent_color || cfg.accent_color || "",
      logo: theme.logo_url || cfg.logo_url || "",
      hero: theme.hero_image_url || cfg.hero_image_url || "",
      primaryHsl: hexToHslTriplet(theme.primary_color || cfg.primary_color || ""),
      accentHsl: hexToHslTriplet(theme.accent_color || cfg.accent_color || ""),
    },
    bookingUrl: cfg.booking_url || "",
    disclaimer:
      content.disclaimer ||
      cfg.disclaimer ||
      "Pré-visualização conceptual não oficial — não representa o negócio.",
    seoTitle: content.seo_title || cfg.seo_title || businessName,
    seoDescription: content.seo_description || cfg.seo_description || heroSub,
  };
  return cached;
}

export const isPreview = (): boolean => getLeadOverlay() !== null;
