import type { SupportedLanguage } from "../../../i18n";

/**
 * タグの種類
 */
export type ExampleTag =
  | "real-estate"
  | "it-department"
  | "manufacturing"
  | "sustainability"
  | "corporate-governance"
  | "healthcare";

/**
 * ファイルの種類
 */
export type FileType = "checklist" | "review" | "knowledge";

/**
 * セットアップの種類
 */
export type SetupType = "knowledge-base" | "mcp";

/**
 * サンプルファイル
 */
export interface ExampleFile {
  id: string;
  name: string;
  type: FileType;
  url: string;
  imagePath?: string; // 画像パス (800x1200px) - グリッドとモーダル両方で使用
}

/**
 * サンプルユースケース
 */
export interface Example {
  id: string;
  name: string;
  tags: ExampleTag[];
  description: string;
  setupTypes?: SetupType[];
  githubUrl?: string;
  files: ExampleFile[];
}

/**
 * 言語別のサンプルデータ
 * i18n の SupportedLanguage (en / ja / ko) ごとに配列を持つ。言語にサンプルが無い場合は en にフォールバックする。
 */
export type ExamplesMetadata = Partial<Record<SupportedLanguage, Example[]>> & {
  en: Example[];
};
