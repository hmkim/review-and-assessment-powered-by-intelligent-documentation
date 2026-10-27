import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import LanguageDetector from "i18next-browser-languagedetector";

// Import translations
import jaTranslation from "./locales/ja.json";
import enTranslation from "./locales/en.json";
import koTranslation from "./locales/ko.json";

/**
 * Languages the UI ships translations for.
 * The same codes are stored as the user's language preference and mapped to
 * the LLM output language on the backend, so keep this list in sync with
 * `backend/src/utils/language.ts`.
 */
export const SUPPORTED_LANGUAGES = ["en", "ja", "ko"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];
export const DEFAULT_LANGUAGE: SupportedLanguage = "en";

export const isSupportedLanguage = (
  lang: string | undefined | null
): lang is SupportedLanguage =>
  (SUPPORTED_LANGUAGES as readonly string[]).includes(lang ?? "");

/**
 * Reduce a locale code to a supported language code.
 * "ko-KR" / "ja_JP" / "EN" -> "ko" / "ja" / "en"; anything else -> DEFAULT_LANGUAGE.
 */
export const normalizeLanguage = (
  lang: string | undefined | null
): SupportedLanguage => {
  const base = (lang ?? "").toLowerCase().split(/[-_]/)[0];
  return isSupportedLanguage(base) ? base : DEFAULT_LANGUAGE;
};

// Configure i18next
i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources: {
      ja: {
        translation: jaTranslation,
      },
      en: {
        translation: enTranslation,
      },
      ko: {
        translation: koTranslation,
      },
    },
    // Only resolve to languages we have bundles for; everything else falls back.
    supportedLngs: [...SUPPORTED_LANGUAGES],
    fallbackLng: DEFAULT_LANGUAGE,
    detection: {
      // Browsers report region-qualified codes ("ko-KR", "ja-JP"). Collapse them to
      // the language part so `i18n.language` is always one of SUPPORTED_LANGUAGES
      // and the value synced to the backend matches its language map.
      convertDetectedLanguage: (lng: string) =>
        lng.toLowerCase().split(/[-_]/)[0],
    },
    debug: process.env.NODE_ENV === "development",
    interpolation: {
      escapeValue: false, // React already escapes values
    },
  });

// Keep <html lang> in sync so font selection (:lang()), hyphenation and
// screen readers follow the active UI language.
const syncDocumentLanguage = (lng: string) => {
  if (typeof document !== "undefined") {
    document.documentElement.lang = normalizeLanguage(lng);
  }
};
i18n.on("languageChanged", syncDocumentLanguage);
syncDocumentLanguage(i18n.language);

export default i18n;
