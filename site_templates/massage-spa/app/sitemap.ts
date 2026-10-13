import type { MetadataRoute } from "next";
import { siteConfig } from "@/lib/site-config";
import { businessInfo } from "@/lib/business";

export default function sitemap(): MetadataRoute.Sitemap {
  const baseUrl = siteConfig.canonicalBaseUrl;
  const locales = siteConfig.locales;
  const lastModified = new Date();

  const routes = ["", "/services", "/prices", "/about", "/reviews", "/contact"];

  const sitemapEntries: MetadataRoute.Sitemap = [];

  locales.forEach((locale) => {
    routes.forEach((route) => {
      sitemapEntries.push({
        url: `${baseUrl}/${locale}${route}`,
        lastModified,
        changeFrequency: route === "" ? "weekly" : "monthly",
        priority: route === "" ? 1.0 : 0.8,
      });
    });

    businessInfo.services.forEach((service) => {
      sitemapEntries.push({
        url: `${baseUrl}/${locale}/services/${service.slug}`,
        lastModified,
        changeFrequency: "monthly",
        priority: 0.7,
      });
    });
  });

  return sitemapEntries;
}
