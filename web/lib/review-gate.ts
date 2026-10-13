import type { Source } from "./types";

// TASK-048: örnek inceleme kapısı. API (approvalGateReasons), DB
// (source_document_review_gate_passes) ve worker (review_gate_passes) ile aynı
// formül. Eşik yoksa (null) eski sıfır tolerans: her örnek onaylı, işaretli 0.
export type SampleReviewGate = {
  thresholdMode: boolean;
  complete: boolean;
  passed: boolean;
  rejectRatePercent: number;
  thresholdPercent: number | null;
};

export function sampleReviewGate(source: Source): SampleReviewGate {
  const sampled = source.sampled_document_count;
  const threshold = source.content_purpose === "pretrain" ? source.pretrain_review_reject_threshold ?? null : null;
  const complete = sampled > 0 && source.reviewed_document_count === sampled;
  const rejectRatePercent = sampled > 0 ? (source.flagged_document_count * 100) / sampled : 0;
  if (threshold === null) {
    return {
      thresholdMode: false,
      complete,
      passed: complete && source.approved_document_count === sampled && source.flagged_document_count === 0,
      rejectRatePercent,
      thresholdPercent: null,
    };
  }
  const thresholdBasisPoints = Math.round(threshold * 100);
  return {
    thresholdMode: true,
    complete,
    passed: complete
      && source.approved_document_count + source.flagged_document_count === sampled
      && source.flagged_document_count * 10000 <= thresholdBasisPoints * sampled,
    rejectRatePercent,
    thresholdPercent: threshold,
  };
}

export function formatPercent(value: number) {
  return `%${value.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

// Kaynak kartı etiketi: "ret oranı %x / eşik %y".
export function rejectRateLabel(gate: SampleReviewGate) {
  return `Ret oranı ${formatPercent(gate.rejectRatePercent)} / eşik ${formatPercent(gate.thresholdPercent ?? 0)}`;
}
