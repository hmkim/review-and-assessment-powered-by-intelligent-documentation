import {
  UserPreferenceModel,
  UserPreferenceDomain,
} from "../domain/model/preference";
import {
  UserPreferenceRepository,
  makePrismaUserPreferenceRepository,
} from "../domain/repository";
import { ValidationError } from "../../../core/errors";
import {
  SUPPORTED_LANGUAGES,
  normalizeLanguage,
} from "../../../../utils/language";

export const getUserPreference = async (params: {
  userId: string;
  deps?: {
    repo?: UserPreferenceRepository;
  };
}): Promise<UserPreferenceModel> => {
  const repo =
    params.deps?.repo || (await makePrismaUserPreferenceRepository());
  const preference = await repo.getUserPreference(params.userId);

  if (!preference) {
    return UserPreferenceDomain.getDefault(params.userId);
  }

  return preference;
};

export interface UpdateLanguageRequest {
  language: string;
}

/**
 * Validates the requested language and reduces it to the stored two-letter
 * code ("ko-KR" -> "ko"). The stored code is later mapped to the LLM output
 * language, so unsupported values must be rejected instead of silently
 * degrading to English.
 */
const resolveRequestedLanguage = (language: unknown): string => {
  const normalized =
    typeof language === "string" ? normalizeLanguage(language) : undefined;
  if (!normalized) {
    throw new ValidationError(
      `Unsupported language. Supported languages: ${SUPPORTED_LANGUAGES.join(", ")}`
    );
  }
  return normalized;
};

export const updateLanguage = async (params: {
  userId: string;
  request: UpdateLanguageRequest;
  deps?: {
    repo?: UserPreferenceRepository;
  };
}): Promise<UserPreferenceModel> => {
  const language = resolveRequestedLanguage(params.request?.language);

  const repo =
    params.deps?.repo || (await makePrismaUserPreferenceRepository());

  const existing = await repo.getUserPreference(params.userId);

  if (!existing) {
    const newPreference = UserPreferenceDomain.create(params.userId, language);
    await repo.saveUserPreference(newPreference);
    return newPreference;
  }

  const updatedPreference = UserPreferenceDomain.updateLanguage(
    existing,
    language
  );
  await repo.updateUserPreference(updatedPreference);
  return updatedPreference;
};
