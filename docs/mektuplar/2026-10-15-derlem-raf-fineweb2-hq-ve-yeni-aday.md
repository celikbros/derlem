# derlem → Gardaş model rafı: v5 ve eski adaylar silindi; FineWeb2-HQ tabanlı yeni aday kayıtlı, inceleme sırada

> **Kimden:** `derlem` · **Kime:** `gardas-modeller` (raf + motor + eğitim birleşik oturumu) · **Tarih:** 2026-10-15
> **Taşıyan:** kurucu · **Tür: BİLGİ** (2026-10-04 mektubundaki "sıradaki korpus FineWeb2-HQ tabanlı" notunun devamı)

## 1. v5 ve eski adaylar silindi

Kurucu kararıyla (2026-10-13 ve 2026-10-14, TASK-043) v1/v3/v4/v5 adayları, üç held-out, Faz-2 ana korpus
ve Faz-2 ham kaynakları silindi. **Raftaki v5 ile ilgili her beklenti kapandı:** v5 teslimi, `wiki_markup_residue`
+150 satırlık örneklem ve v5 tabanlı teslim mektubu artık yok.

## 2. FineWeb2-HQ `tur_Latn` tam alındı

`epfml/FineWeb2-HQ`, revision `c0c06e94fd3a44ae9e802b2b0fc533817601eb5e`: 8.578.808 belge (105 parça), embeddings
indirilmedi. Manifest SHA256: `d28fe0d13770bd0c16c0f3442f1ec366d663983061394f0198f4a2db08e94e0c`.

## 3. Hakem örneklemesi (TASK-047)

Kılavuz `juri-siki-v1@50e993d6` (sıkı), hakem Sonnet; 400'lük karma kör dosya, iki bağımsız geçiş.
Çöp (çöp + emin değilim): FineWeb2-HQ **%46,5** [39,7–53,4] (makine çevirisi 42/93), Faz-2 ana korpus **%48,0**
[41,2–54,9]. Test-tekrar κ: 0,91 / 0,84.

## 4. `tr-web-v4` ve B hedefi (TASK-046)

`tr-web-v4` = `tr-web-v3` + `machine_translation` + `commercial_page`. Kurucu **B** hedefini seçti
(yanlış atma tavanı %7,5). Hakem yeniden koşusunda çöp oranı %47,0 → %39,0. Yargıç kimliği:
`tr-web-v4@4559662a171d`.

## 5. Yeni aday ve held-out (TASK-049, TASK-050)

| | Aday | Held-out |
|---|---|---|
| Kaynak adı | `fineweb2_hq_tur_latn_clean_candidate_trweb4B_xdedup_20261014` | `fineweb2_hq_tur_latn_heldout_trweb4B_20261014` |
| Kaynak kimliği | `07a2b7e0-853b-4ce2-8a8c-653c1f31d921` | `ffde0f72-97d7-48a9-829e-eed9a77557d1` |
| Belge | 6.601.402 | 2.652 |
| Nesne SHA256 | `97f300a93cdacaffcfe952752be8d3109d0b39df2c9c37772c0ee6a682d695a0` | `e498e6fbf0232b39808410546b380427e4fb35cbb0f29d0fabb1542cbe2ab0ef` |
| Bayt | 15.243.666.531 | — |

8.578.808 belgeden atılanlar: makine çevirisi 1.766.036 · ticari sayfa 197.177 · v3 nedenleri 72.219 ·
kişisel veri 86.602 · yakın kopya 1.585 · birebir kopya 22 · Faz-2 ile ortak 1.149 (ayrı adımda, sonradan çıkarıldı).

## 6. Kapılar ve sıradaki adım

- Kişisel veri: temiz. Birebir kopya: yok. Yakın kopya: `unique`.
- Aday ile ilgisiz kaynaklar arasında ortak belge: 0 (11.995.448 satır, 11 kaynak karşılaştırıldı).
- 200 örnek incelemesi %10 reddetme eşiğiyle (TASK-048) sırada; ardından dondurma.

## 7. Eval kayıtları yerinde

`karar-v1` (`fa772e47-9647-411a-913e-6eaa6a184919`), `karar-v2` tam (`4b0ab363-f4ec-4a65-8fea-6ec8273f9582`) ve
karar-v2 geliştirme (`109fefff-686f-49b8-99bb-6138e057e4f6`) `eval` olarak kayıtlı kalıyor. Dondurmada
dekontaminasyon kapıları bu üçüne karşı koşacak.

## 8. Sizden beklenen / bizden beklenen

**Sizden beklenen:** yok; bu bir bilgi mektubu.

**Bizden beklenen:** inceleme → dondurma → model kartı satırı (sürüm kimliği ve SHA'larla), teslim mektubuyla birlikte.
