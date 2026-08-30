import { expect, test } from "@playwright/test";

import { readableParagraphs } from "../../lib/readable-document";

test("builds readable paragraphs without losing normalized text", () => {
  const raw = "  İlk   cümle. İkinci cümle! Üçüncü?  ";
  const paragraphs = readableParagraphs(raw, 25);

  expect(paragraphs).toEqual(["İlk cümle. İkinci cümle!", "Üçüncü?"]);
  expect(paragraphs.join(" ")).toBe(raw.replace(/\s+/gu, " ").trim());
});

test("chunks long punctuation-free spam for display", () => {
  const raw = Array.from({ length: 80 }, (_, index) => `etiket${index}`).join(" ");
  const paragraphs = readableParagraphs(raw, 90);

  expect(paragraphs.length).toBeGreaterThan(1);
  expect(paragraphs.join(" ")).toBe(raw);
});

test("returns no paragraphs for blank content", () => {
  expect(readableParagraphs(" \r\n\t ")).toEqual([]);
});
