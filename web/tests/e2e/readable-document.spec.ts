import { expect, test } from "@playwright/test";

import { isSectionLabel, readableParagraphs } from "../../lib/readable-document";

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

// Worker kanonik kaydı etiketli bölümler halinde saklar (TASK-002 S6); inceleyici
// düzeltme çiftinin iki tarafını ayrı ayrı görmeli, tek paragrafa ezilmiş değil.
test("keeps labelled sections of an edit pair apart", () => {
  const review = [
    "[Kullanıcı]\nIşık hızı nedir?",
    "[Seçilen yanıt — chosen]\nBoşlukta yaklaşık 299.792 km/s'dir.",
    "[Reddedilen yanıt — rejected]\nSaniyede 300 km'dir.",
  ].join("\n\n");

  const paragraphs = readableParagraphs(review);

  expect(paragraphs).toEqual([
    "[Kullanıcı]",
    "Işık hızı nedir?",
    "[Seçilen yanıt — chosen]",
    "Boşlukta yaklaşık 299.792 km/s'dir.",
    "[Reddedilen yanıt — rejected]",
    "Saniyede 300 km'dir.",
  ]);
  expect(paragraphs.filter(isSectionLabel)).toHaveLength(3);
});

test("handles CRLF section breaks from stored text", () => {
  expect(readableParagraphs("[Kullanıcı]\r\nSoru?\r\n\r\n[Asistan]\r\nCevap.")).toEqual([
    "[Kullanıcı]",
    "Soru?",
    "[Asistan]",
    "Cevap.",
  ]);
});

test("does not treat bracketed text inside ordinary prose as a label", () => {
  expect(readableParagraphs("[not] bir cümle.\ndevamı")).toEqual(["[not] bir cümle. devamı"]);
  expect(isSectionLabel("[not] bir cümle.")).toBe(false);
  // Etiket satırının altında gövde yoksa tek satırlık "[x]" düz metin olarak kalır.
  expect(readableParagraphs("[yalnız]")).toEqual(["[yalnız]"]);
});
