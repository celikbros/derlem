export async function requestJSON<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, cache: "no-store" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const reasons = Array.isArray(payload?.error?.reasons)
      ? ` (${payload.error.reasons.map((reason: string) => gateReasonLabels[reason] ?? reason).join(", ")})`
      : "";
    throw new Error(`${payload?.error?.message ?? "İşlem tamamlanamadı."}${reasons}`);
  }
  return payload as T;
}

const gateReasonLabels: Record<string, string> = {
  reason_required: "gerekçe zorunlu",
  file_not_ingested: "dosya içe alınmadı",
  rights_not_cleared: "haklar temizlenmedi",
  license_evidence_missing: "lisans kanıtı eksik",
  pii_not_clear: "PII taraması temiz değil",
  exact_duplicate_not_clear: "dosya dedup temiz degil",
  normalized_dedup_not_clear: "normalize dedup temiz degil",
  documents_not_sampled: "belge ornekleri hazirlanmadi",
  document_sample_review_incomplete: "belge ornek incelemesi tamamlanmadi",
  already_approved: "kaynak zaten onaylı",
};

export function messageFrom(error: unknown) {
  return error instanceof Error ? error.message : "İşlem tamamlanamadı.";
}
