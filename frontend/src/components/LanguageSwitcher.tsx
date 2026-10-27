import React, { useState } from "react";
import { useTranslation } from "react-i18next";
import { HiTranslate, HiChevronDown, HiChevronRight, HiCheck } from "react-icons/hi";
import { useLanguage } from "../contexts/LanguageContext";
import { SUPPORTED_LANGUAGES, SupportedLanguage } from "../i18n";

/**
 * 言語切り替えメニュー
 * サイドバーの「プロンプト管理」サブメニューと同じ開閉パターンで、
 * 対応言語を自国語表記で一覧表示し、選択中の言語をハイライトします。
 */
const LanguageSwitcher: React.FC = () => {
  const { t } = useTranslation();
  const { language, changeLanguage } = useLanguage();
  const [isOpen, setIsOpen] = useState(false);

  const handleSelect = (lang: SupportedLanguage) => {
    changeLanguage(lang);
    setIsOpen(false);
  };

  return (
    <div>
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
        className="flex w-full items-center rounded-md px-4 py-2 text-sm transition-colors hover:bg-aws-sea-blue-hover-light">
        <HiTranslate className="mr-2 h-4 w-4" />
        {/* 言語名はどの UI 言語でも自国語表記（language.* は全ロケール共通） */}
        {t(`language.${language}`)}
        <span className="ml-auto">
          {isOpen ? (
            <HiChevronDown className="h-4 w-4" />
          ) : (
            <HiChevronRight className="h-4 w-4" />
          )}
        </span>
      </button>

      {isOpen && (
        <ul role="listbox" aria-label={t("sidebar.menu")} className="ml-6 mt-1 space-y-1">
          {SUPPORTED_LANGUAGES.map((lang) => {
            const isSelected = lang === language;
            return (
              <li key={lang} role="option" aria-selected={isSelected}>
                <button
                  type="button"
                  lang={lang}
                  onClick={() => handleSelect(lang)}
                  className={`flex w-full items-center rounded-md px-4 py-2 text-sm transition-colors ${
                    isSelected
                      ? "bg-aws-sea-blue-light text-aws-font-color-white-light"
                      : "text-aws-font-color-white-light hover:bg-aws-sea-blue-hover-light"
                  }`}>
                  {t(`language.${lang}`)}
                  {isSelected && <HiCheck className="ml-auto h-4 w-4" />}
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
};

export default LanguageSwitcher;
