const sentenceBoundary = /([.!?…])\s+/gu;

export function readableParagraphs(text: string, targetLength = 520): string[] {
  const normalized = text.replace(/\s+/gu, " ").trim();
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
