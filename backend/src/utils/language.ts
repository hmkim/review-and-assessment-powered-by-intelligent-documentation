/**
 * Language utility functions
 *
 * The frontend stores the user's UI language (two-letter code) as the user
 * preference, and these helpers turn that code into the language name that
 * is substituted into the LLM prompts. Keep SUPPORTED_LANGUAGES in sync with
 * `frontend/src/i18n/index.ts`.
 */

export const SUPPORTED_LANGUAGES = ["en", "ja", "ko"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

// Default language if user preference is not available
export const DEFAULT_LANGUAGE: SupportedLanguage = "en";

/**
 * Full language names (in English) used in prompts, e.g.
 * "YOU MUST GENERATE THE ENTIRE OUTPUT IN Korean".
 */
const LANGUAGE_NAMES: Record<SupportedLanguage, string> = {
  en: "English",
  ja: "Japanese",
  ko: "Korean",
  // Add more languages here as needed (and in the frontend bundle list)
};

export const isSupportedLanguage = (
  languageCode: string | undefined | null
): languageCode is SupportedLanguage =>
  (SUPPORTED_LANGUAGES as readonly string[]).includes(languageCode ?? "");

/**
 * Normalizes a language code to a supported two-letter code, or returns
 * `undefined` when the code is not supported.
 *
 * Accepts region/script-qualified codes and mixed case:
 * "ko-KR" / "ja_JP" / "EN" -> "ko" / "ja" / "en"
 * @param languageCode Raw language code (e.g. from a browser or the DB)
 */
export const normalizeLanguage = (
  languageCode: string | undefined | null
): SupportedLanguage | undefined => {
  if (typeof languageCode !== "string") {
    return undefined;
  }
  const base = languageCode.trim().toLowerCase().split(/[-_]/)[0];
  return isSupportedLanguage(base) ? base : undefined;
};

/**
 * Maps language code to full language name
 * @param languageCode Language code (e.g. 'en', 'ja', 'ko', 'ko-KR')
 * @returns Full language name (e.g. 'English', 'Japanese', 'Korean');
 *          falls back to the DEFAULT_LANGUAGE name for unsupported codes
 */
export const getLanguageName = (languageCode: string): string => {
  const normalized = normalizeLanguage(languageCode) ?? DEFAULT_LANGUAGE;
  return LANGUAGE_NAMES[normalized];
};
