import React, { createContext, useContext, useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useUpdateLanguage } from "../features/user-preference/hooks/useUserPreferenceMutations";
import { useAuth } from "./AuthContext";
import { normalizeLanguage, SupportedLanguage } from "../i18n";

type LanguageContextType = {
  language: SupportedLanguage;
  changeLanguage: (lang: string) => void;
};

const LanguageContext = createContext<LanguageContextType | undefined>(
  undefined
);

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const { i18n } = useTranslation();
  // i18next has already resolved the detected/stored language against the
  // supported list at this point; normalize defensively so the context never
  // holds a region-qualified or unsupported code.
  const [language, setLanguage] = useState<SupportedLanguage>(() =>
    normalizeLanguage(i18n.language)
  );
  const { updateLanguage } = useUpdateLanguage();
  const { isAuthenticated } = useAuth();

  const changeLanguage = (lang: string) => {
    const normalized = normalizeLanguage(lang);

    // フロントエンドの言語設定を更新（常に真）
    i18n.changeLanguage(normalized);
    setLanguage(normalized);

    // バックエンドに同期（未認証時は 401 になるためスキップ）
    if (!isAuthenticated) {
      return;
    }
    updateLanguage({ language: normalized }).catch((error) => {
      console.error("Failed to sync language with backend:", error);
    });
  };

  // 認証済みになったら現在の言語をバックエンドと同期（未認証時は 401 のためスキップ）
  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    updateLanguage({ language: normalizeLanguage(i18n.language) }).catch(
      (error) => {
        console.error("Failed to sync language with backend:", error);
      }
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isAuthenticated]);

  return (
    <LanguageContext.Provider value={{ language, changeLanguage }}>
      {children}
    </LanguageContext.Provider>
  );
};

export const useLanguage = (): LanguageContextType => {
  const context = useContext(LanguageContext);
  if (context === undefined) {
    throw new Error("useLanguage must be used within a LanguageProvider");
  }
  return context;
};
