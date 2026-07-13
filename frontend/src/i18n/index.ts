// i18next-Setup. Default-Sprache Deutsch (DACH-Zielmarkt) - Erkennung
// bewusst NUR aus localStorage (keine Browser-Sprache-Autodetektion), damit
// jeder Erstbesuch konsistent auf Deutsch startet, bis der Nutzer aktiv
// über den Sprachumschalter wechselt.

import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import de from "./locales/de.json";
import en from "./locales/en.json";
import fa from "./locales/fa.json";

export const SUPPORTED_LANGUAGES = ["de", "en", "fa"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
export const RTL_LANGUAGES: SupportedLanguage[] = ["fa"];

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      de: { translation: de },
      en: { translation: en },
      fa: { translation: fa },
    },
    fallbackLng: "de",
    supportedLngs: [...SUPPORTED_LANGUAGES],
    detection: {
      order: ["localStorage"],
      caches: ["localStorage"],
      lookupLocalStorage: "language",
    },
    interpolation: { escapeValue: false },
  });

function applyDirection(language: string): void {
  const isRtl = RTL_LANGUAGES.includes(language as SupportedLanguage);
  document.documentElement.dir = isRtl ? "rtl" : "ltr";
  document.documentElement.lang = language;
}

applyDirection(i18n.resolvedLanguage ?? i18n.language ?? "de");
i18n.on("languageChanged", applyDirection);

export default i18n;
