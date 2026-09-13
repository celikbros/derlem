const sentenceBoundary = /([.!?…])\s+/gu;
// Worker'ın kanonik kayıt inceleme metnindeki bölüm etiketi: tek satır, köşeli
// parantez içinde ("[Kullanıcı]", "[Seçilen yanıt — chosen]").
const sectionLabel = /^\[[^\]\n]{1,80}\]$/u;

/**
 * Okuma görünümü paragrafları. Metin boş satırla bölümlere ayrılmışsa bölümler
 * korunur ve bölümün ilk satırındaki "[etiket]" kendi paragrafı olur; her bölümün
 * içinde boşluk ezilip cümlelere bölünür. Tek bloklu belgelerde davranış öncekiyle
 * aynıdır (TASK-002 S6: inceleyici düzeltmenin iki tarafını ayrı görür).
 */
export function readableParagraphs(text: string, targetLength = 520): string[] {
  return text
    .split(/\n\s*\n/u)
    .flatMap((block) => blockParagraphs(block, targetLength));
}

export function isSectionLabel(paragraph: string): boolean {
  return sectionLabel.test(paragraph);
}

function blockParagraphs(block: string, targetLength: number): string[] {
  const lines = block.split("\n");
  const firstLine = lines[0]?.trim() ?? "";
  if (lines.length > 1 && sectionLabel.test(firstLine)) {
    return [firstLine, ...blockParagraphs(lines.slice(1).join("\n"), targetLength)];
  }

  const normalized = block.replace(/\s+/gu, " ").trim();
  if (!normalized) return [];

  const sentences = normalized
    .replace(sentenceBoundary, "$1\n")
    .split("\n")
    .map((sentence) => sentence.trim())
    .filter(Boolean);

  const paragraphs: string[] = [];
  let current = "";

  const pushCurrent = () => {
    if (!current) return;
    paragraphs.push(current);
    current = "";
  };

  for (const sentence of sentences) {
    if (sentence.length > targetLength * 1.35) {
      pushCurrent();
      for (const chunk of chunkWords(sentence, targetLength)) {
        paragraphs.push(chunk);
      }
      continue;
    }

    const candidate = current ? `${current} ${sentence}` : sentence;
    if (current && candidate.length > targetLength) {
      pushCurrent();
      current = sentence;
    } else {
      current = candidate;
    }
  }

  pushCurrent();
  return paragraphs;
}

function chunkWords(text: string, targetLength: number): string[] {
  const chunks: string[] = [];
  let current = "";

  for (const word of text.split(" ")) {
    const candidate = current ? `${current} ${word}` : word;
    if (current && candidate.length > targetLength) {
      chunks.push(current);
      current = word;
    } else {
      current = candidate;
    }
  }

  if (current) chunks.push(current);
  return chunks;
}
