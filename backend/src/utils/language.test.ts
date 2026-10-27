import { describe, it, expect } from "vitest";
import {
  DEFAULT_LANGUAGE,
  SUPPORTED_LANGUAGES,
  getLanguageName,
  isSupportedLanguage,
  normalizeLanguage,
} from "./language";

describe("language utils", () => {
  it("supports en, ja and ko", () => {
    expect([...SUPPORTED_LANGUAGES]).toEqual(["en", "ja", "ko"]);
    expect(DEFAULT_LANGUAGE).toBe("en");
  });

  describe("normalizeLanguage", () => {
    it("returns supported two-letter codes unchanged", () => {
      expect(normalizeLanguage("en")).toBe("en");
      expect(normalizeLanguage("ja")).toBe("ja");
      expect(normalizeLanguage("ko")).toBe("ko");
    });

    it("strips region/script qualifiers and normalizes case", () => {
      expect(normalizeLanguage("ko-KR")).toBe("ko");
      expect(normalizeLanguage("ja_JP")).toBe("ja");
      expect(normalizeLanguage("EN-us")).toBe("en");
      expect(normalizeLanguage(" KO ")).toBe("ko");
    });

    it("returns undefined for unsupported or invalid input", () => {
      expect(normalizeLanguage("de")).toBeUndefined();
      expect(normalizeLanguage("zh-Hant-TW")).toBeUndefined();
      expect(normalizeLanguage("")).toBeUndefined();
      expect(normalizeLanguage(undefined)).toBeUndefined();
      expect(normalizeLanguage(null)).toBeUndefined();
    });
  });

  describe("isSupportedLanguage", () => {
    it("only accepts exact supported codes", () => {
      expect(isSupportedLanguage("ko")).toBe(true);
      expect(isSupportedLanguage("ko-KR")).toBe(false);
      expect(isSupportedLanguage("KO")).toBe(false);
      expect(isSupportedLanguage(undefined)).toBe(false);
    });
  });

  describe("getLanguageName", () => {
    it("maps supported codes to prompt language names", () => {
      expect(getLanguageName("en")).toBe("English");
      expect(getLanguageName("ja")).toBe("Japanese");
      expect(getLanguageName("ko")).toBe("Korean");
    });

    it("accepts region-qualified and upper-case codes", () => {
      expect(getLanguageName("ko-KR")).toBe("Korean");
      expect(getLanguageName("ja-JP")).toBe("Japanese");
      expect(getLanguageName("JA")).toBe("Japanese");
    });

    it("falls back to English for unsupported codes", () => {
      expect(getLanguageName("de")).toBe("English");
      expect(getLanguageName("")).toBe("English");
    });
  });
});
