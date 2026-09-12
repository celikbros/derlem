// Kaynak PII durumunun ekrandaki metni. Kısa durum kodları (clear, flagged, …)
// olduğu gibi gösterilir; not_evaluated kendini açıklamadığı için açıklanır:
// tarayıcının dile özgü dedektörleri bu kaynağın dilinde çalışmaz, sıfır bulgu
// "temiz" değil "bakılamadı" demektir (worker/src/derlem_worker/pii.py).
export const PII_NOT_EVALUATED = "not_evaluated";

export function piiStatusText(status: string): string {
  return status === PII_NOT_EVALUATED ? "değerlendirilmedi — dil desteklenmiyor" : status;
}
