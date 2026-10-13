import type { Source } from "./types";

// TASK-047: kaynak kartında dört kalite sayısı. Worker (derlem_worker.jury)
// sayıları sources.source_metadata.quality_numbers altına yazar (migration yok);
// insan ret oranı kaynak satırının canlı sayaçlarından hesaplanır.
export type QualityRate = {
  count: number;
  n: number;
  rate: number | null;
  low: number | null;
  high: number | null;
};

export type QualityNumbers = {
  schema: "derlem.quality-numbers.v1";
  computed_at: string;
  run_id: string;
  judge_id: string | null;
  judge_model: string | null;
  rubric: { id: string; sha256: string };
  sample: { n: number; seed: number; method: string; population_documents: number; source_kind: string };
  pii: QualityRate & { scanner_version: string; population?: { hits: number; hits_per_1k_documents: number | null } };
  rule: QualityRate & { policy: string; status: string | null };
  jury: Partial<QualityRate> & {
    status: "judged" | "judge_unavailable";
    missing?: number;
    retest?: { n: number; agreement_binary: number | null; kappa_binary: number | null } | null;
  };
  decisions: { sha256: string; rows: number } | null;
  cost: { calls: number; estimated_usd: number | null; price_table: string } | null;
};

export function readQualityNumbers(source: Source): QualityNumbers | null {
  const value = source.source_metadata?.quality_numbers;
  if (!value || typeof value !== "object") return null;
  const numbers = value as Partial<QualityNumbers>;
  if (numbers.schema !== "derlem.quality-numbers.v1" || !numbers.pii || !numbers.rule || !numbers.jury) return null;
  return numbers as QualityNumbers;
}

const WILSON_Z = 1.959963985;

// jury_scoring.wilson ile aynı formül (Wilson %95).
export function wilson(successes: number, total: number): [number, number] {
  if (total <= 0) return [0, 1];
  const phat = successes / total;
  const denominator = 1 + (WILSON_Z * WILSON_Z) / total;
  const centre = (phat + (WILSON_Z * WILSON_Z) / (2 * total)) / denominator;
  const margin = (WILSON_Z * Math.sqrt((phat * (1 - phat)) / total + (WILSON_Z * WILSON_Z) / (4 * total * total))) / denominator;
  return [Math.max(0, centre - margin), Math.min(1, centre + margin)];
}

// İnsan ret oranı: (ret + sensitive_review) / incelenen örnek. İnceleme yoksa null.
export function humanRejectRate(source: Source): QualityRate | null {
  const reviewed = source.reviewed_document_count;
  if (!reviewed || reviewed <= 0) return null;
  const rejected = source.flagged_document_count;
  const [low, high] = wilson(rejected, reviewed);
  return { count: rejected, n: reviewed, rate: rejected / reviewed, low, high };
}

function percent(value: number) {
  return `%${(value * 100).toLocaleString("tr-TR", { maximumFractionDigits: 1, minimumFractionDigits: value > 0 && value < 0.1 ? 1 : 0 })}`;
}

export function rateLabel(rate: Partial<QualityRate> | null | undefined) {
  if (!rate || rate.rate === null || rate.rate === undefined || !rate.n) return "—";
  return percent(rate.rate);
}

export function intervalLabel(rate: Partial<QualityRate> | null | undefined) {
  if (!rate || rate.low === null || rate.low === undefined || rate.high === null || rate.high === undefined || !rate.n) return "";
  return `${percent(rate.low)}–${percent(rate.high)} · n=${rate.n}`;
}

export function juryLabel(numbers: QualityNumbers | null) {
  if (!numbers) return "Ölçülmedi";
  if (numbers.jury.status === "judge_unavailable") return "Hüküm bekliyor";
  return rateLabel(numbers.jury);
}
