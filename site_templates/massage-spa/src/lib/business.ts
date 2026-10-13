export const businessInfo = {
  name: "Kaapora Massagem Terapêutica",
  legalName: "Kaapora",
  description: {
    pt: "Terapias Complementares & Massagem Terapêutica no Porto. Um espaço de acolhimento e cuidado por Daiane Dias.",
    en: "Complementary Therapies & Therapeutic Massage in Porto. A space of welcome and care by Daiane Dias.",
  },

  contact: {
    phone: "+351911150331",
    phoneDisplay: "+351 911 150 331",
    whatsapp: "https://wa.me/351911150331",
    whatsappMessage: {
      pt: "Olá! Gostaria de agendar uma sessão.",
      en: "Hello! I would like to book a session.",
    },
  },

  address: {
    streetAddress: "Rua de Santo Isidro, 134",
    addressLocality: "Porto",
    addressRegion: "Porto",
    postalCode: "4000-473",
    addressCountry: "PT",
  },

  geo: {
    latitude: 41.1537,
    longitude: -8.6033,
  },

  openingHours: {
    schedule: "Su-Tu,Th-Fr",
    display: {
      pt: "Domingo a Terça, Quinta e Sexta",
      en: "Sunday to Tuesday, Thursday and Friday",
    },
  },

  priceRange: "€€",

  services: [
    {
      slug: "massagem-relaxante",
      name: { pt: "Massagem Relaxante", en: "Relaxation Massage" },
      price: 25,
      duration: 60,
    },
    {
      slug: "massagem-geotermica",
      name: { pt: "Massagem Geotérmica", en: "Hot Stone Massage" },
      price: 25,
      duration: 60,
    },
    {
      slug: "massagem-indiana",
      name: { pt: "Massagem Indiana", en: "Indian Head Massage" },
      price: 25,
      duration: 60,
    },
    {
      slug: "massagem-facial",
      name: { pt: "Massagem Facial", en: "Facial Massage" },
      price: 25,
      duration: 60,
    },
    {
      slug: "massagem-modeladora",
      name: { pt: "Massagem Modeladora", en: "Body Sculpting Massage" },
      price: 30,
      duration: 60,
    },
    {
      slug: "drenagem-linfatica",
      name: { pt: "Drenagem Linfática", en: "Lymphatic Drainage" },
      price: 25,
      duration: 60,
    },
    {
      slug: "shiatsu",
      name: { pt: "Shiatsu", en: "Shiatsu" },
      price: 25,
      duration: 60,
    },
    {
      slug: "reflexologia",
      name: { pt: "Reflexologia / Escalda-pés", en: "Reflexology / Foot Soak" },
      price: 25,
      duration: 60,
    },
    {
      slug: "liberacao-miofascial",
      name: { pt: "Liberação Miofascial", en: "Myofascial Release" },
      price: 25,
      duration: 60,
    },
  ],

  combos: [
    {
      slug: "relaxante-miofascial",
      name: { pt: "Relaxante + Miofascial", en: "Relaxation + Myofascial" },
      price: 38,
      duration: 90,
    },
    {
      slug: "relaxante-escaldapes",
      name: { pt: "Relaxante + Escalda-pés", en: "Relaxation + Foot Soak" },
      price: 38,
      duration: 90,
    },
    {
      slug: "drenagem-modeladora",
      name: { pt: "Drenagem + Modeladora", en: "Drainage + Sculpting" },
      price: 43,
      duration: 90,
    },
  ],

  sameAs: ["https://www.instagram.com/kaapora_kaapora/"],

  therapist: {
    name: "Daiane Dias",
  },
} as const;

export type Service = (typeof businessInfo.services)[number];
export type Combo = (typeof businessInfo.combos)[number];
