import type { Locale } from "@/i18n-config";
import type { Dictionary } from "@/lib/dictionaries";
import { NavbarClient } from "./NavbarClient";

interface NavbarProps {
  lang: Locale;
  dict: Dictionary;
}

export function Navbar({ lang, dict }: NavbarProps) {
  return <NavbarClient lang={lang} dict={dict} />;
}
