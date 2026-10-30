import { describe, it, expect } from "vitest";
import { collectOutputText } from "./llm-processing";

describe("collectOutputText", () => {
  it("returns plain text when the response has only text blocks", () => {
    const msg = { content: [{ text: '[{"name":"a"' }, { text: "}]" }] };
    expect(collectOutputText(msg)).toBe('[{"name":"a"}]');
  });

  it("keeps cited spans from citationsContent blocks in order", () => {
    // Shape returned by Converse when document citations are enabled: the cited
    // part of the description is delivered in a citationsContent block.
    const msg = {
      content: [
        { text: '[{"name":"대지면적 산정","description":"' },
        {
          citationsContent: {
            content: [
              { text: "대지면적이 대지의 수평투영면적으로 산정되었는지" },
            ],
            citations: [{ title: "ChecklistDocument", location: {} }],
          },
        },
        { text: ' 확인한다.","parent_id":0}]' },
      ],
    };
    const text = collectOutputText(msg);
    expect(JSON.parse(text)).toEqual([
      {
        name: "대지면적 산정",
        description:
          "대지면적이 대지의 수평투영면적으로 산정되었는지 확인한다.",
        parent_id: 0,
      },
    ]);
  });

  it("returns an empty string for a missing message", () => {
    expect(collectOutputText(undefined)).toBe("");
    expect(collectOutputText({})).toBe("");
  });
});
