import { describe, it, expect } from "vitest";

// @/lib/mentions does not exist yet — all tests must fail with module-not-found.

describe("parseMentions", () => {
  it("parseMentions('@Cleo please review') returns [{name:'Cleo',start:0,end:5}]", async () => {
    const { parseMentions } = await import("@/lib/mentions");
    const result = parseMentions("@Cleo please review");
    expect(result).toHaveLength(1);
    expect(result[0].name).toBe("Cleo");
    expect(result[0].start).toBe(0);
    expect(result[0].end).toBe(5);
  });

  it("parseMentions('no mentions here') returns []", async () => {
    const { parseMentions } = await import("@/lib/mentions");
    const result = parseMentions("no mentions here");
    expect(result).toHaveLength(0);
  });

  it("parseMentions('@Cleo and @Pria') returns two results", async () => {
    const { parseMentions } = await import("@/lib/mentions");
    const result = parseMentions("@Cleo and @Pria");
    expect(result).toHaveLength(2);
    expect(result.map((r: { name: string }) => r.name)).toEqual(
      expect.arrayContaining(["Cleo", "Pria"])
    );
  });
});

describe("renderMentionText", () => {
  it("wraps @Name in span.mention", async () => {
    const { renderMentionText } = await import("@/lib/mentions");
    const result = renderMentionText("Hello @Cleo");
    expect(result).toContain('<span class="mention">@Cleo</span>');
  });
});

describe("extractMentionedNames", () => {
  it("returns unique names array", async () => {
    const { extractMentionedNames } = await import("@/lib/mentions");
    const result = extractMentionedNames("@Cleo and @Pria and @Cleo again");
    expect(Array.isArray(result)).toBe(true);
    // Should be unique
    const unique = [...new Set(result)];
    expect(result).toHaveLength(unique.length);
    expect(result).toContain("Cleo");
    expect(result).toContain("Pria");
  });
});
