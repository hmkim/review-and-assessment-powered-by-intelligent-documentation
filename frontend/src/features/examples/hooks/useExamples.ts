import { useMemo } from "react";
import { Example, ExampleTag, ExamplesMetadata } from "../types";
import examplesMetadata from "../data/examples-metadata.json";
import type { SupportedLanguage } from "../../../i18n";

const metadata = examplesMetadata as ExamplesMetadata;

/**
 * サンプルデータの取得とフィルタリングを行うカスタムフック
 * 選択されたタグと言語に基づいてサンプルをフィルタリングします。
 * 指定言語のサンプルが無い場合は英語のサンプルを返し、isFallback を true にします。
 */
export function useExamples(
  language: SupportedLanguage,
  selectedTags: ExampleTag[]
) {
  return useMemo(() => {
    const own = metadata[language] ?? [];
    const isFallback = own.length === 0 && language !== "en";
    const languageExamples: Example[] = isFallback ? metadata.en : own;

    // 選択されたタグのいずれかを持つサンプルをフィルタリング (OR条件)
    const examples =
      selectedTags.length === 0
        ? languageExamples
        : languageExamples.filter((example) =>
            example.tags.some((tag) => selectedTags.includes(tag))
          );

    return { examples, isFallback };
  }, [language, selectedTags]);
}
