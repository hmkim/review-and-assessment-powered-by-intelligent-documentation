import { describe, it, expect, vi } from "vitest";
import { updateLanguage } from "./preference";
import { ValidationError } from "../../../core/errors/application-errors";
import type { UserPreferenceRepository } from "../domain/repository";
import type { UserPreferenceModel } from "../domain/model/preference";

const makeRepo = (existing: UserPreferenceModel | null) => {
  const repo: UserPreferenceRepository = {
    getUserPreference: vi.fn().mockResolvedValue(existing),
    saveUserPreference: vi.fn().mockResolvedValue(undefined),
    updateUserPreference: vi.fn().mockResolvedValue(undefined),
  };
  return repo;
};

describe("updateLanguage", () => {
  it("creates a preference with the normalized language code", async () => {
    const repo = makeRepo(null);

    const result = await updateLanguage({
      userId: "user-1",
      request: { language: "ko-KR" },
      deps: { repo },
    });

    expect(result.language).toBe("ko");
    expect(repo.saveUserPreference).toHaveBeenCalledWith(
      expect.objectContaining({ userId: "user-1", language: "ko" })
    );
    expect(repo.updateUserPreference).not.toHaveBeenCalled();
  });

  it("updates an existing preference with the normalized language code", async () => {
    const existing: UserPreferenceModel = {
      id: "pref-1",
      userId: "user-1",
      language: "ja",
      createdAt: new Date("2026-01-01T00:00:00Z"),
      updatedAt: new Date("2026-01-01T00:00:00Z"),
    };
    const repo = makeRepo(existing);

    const result = await updateLanguage({
      userId: "user-1",
      request: { language: "KO" },
      deps: { repo },
    });

    expect(result.language).toBe("ko");
    expect(repo.updateUserPreference).toHaveBeenCalledWith(
      expect.objectContaining({ id: "pref-1", language: "ko" })
    );
    expect(repo.saveUserPreference).not.toHaveBeenCalled();
  });

  it.each(["de", "", "   ", "kor", "zh-Hant-TW"])(
    "rejects unsupported language %j without touching the repository",
    async (language) => {
      const repo = makeRepo(null);

      await expect(
        updateLanguage({
          userId: "user-1",
          request: { language },
          deps: { repo },
        })
      ).rejects.toBeInstanceOf(ValidationError);

      expect(repo.getUserPreference).not.toHaveBeenCalled();
      expect(repo.saveUserPreference).not.toHaveBeenCalled();
      expect(repo.updateUserPreference).not.toHaveBeenCalled();
    }
  );

  it("rejects a missing language", async () => {
    const repo = makeRepo(null);

    await expect(
      updateLanguage({
        userId: "user-1",
        request: { language: undefined as unknown as string },
        deps: { repo },
      })
    ).rejects.toBeInstanceOf(ValidationError);
  });
});
