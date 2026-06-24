# Gorev Taksonomisi

## MVP Gorevleri

### 1. Sadelestirme

Katilimci, verilen metni anlam kaybi olmadan daha sade Turkceyle yazar.

Ornek:

- Girdi: Teknik veya resmi bir paragraf
- Cikti: Daha sade, dogal ve anlasilir Turkce
- Etiket: `simplification`

### 2. Metinden Soru-Cevap

Katilimci, verilen metne dayali sorular ve cevaplar uretir. Cevap metinde bulunmayan bilgi eklememelidir.

Etiket: `grounded_qa`

### 3. Model Cevabi Degerlendirme

Katilimci, modelin cevabini puanlar ve gerekirse duzeltir.

Olcutler:

- Dogru mu?
- Soruyu cevapliyor mu?
- Turkcesi dogal mi?
- Gereksiz uydurma var mi?

Etiket: `answer_review`

### 4. Dogal Turkceye Cevirme

Katilimci, bozuk veya ceviri kokan Turkceyi dogal hale getirir.

Etiket: `naturalize_tr`

## Ikinci Faz Gorevleri

- Iki cevap arasinda tercih
- Gerekceli siniflandirma
- Kisa metin ozeti
- Uzun metin ozeti
- Dilbilgisi ve yazim duzeltme
- Alan uzmanligi gerektiren kontrollu veri uretimi

## Gorev Tasarim Kurali

Kotu gorev:

> Turkce paragraf yaz.

Iyi gorev:

> Asagidaki metni, anlam kaybi olmadan 12 yasindaki bir ogrencinin anlayacagi sekilde sadelestir. Sonunda metne dayali 3 kontrol sorusu uret.
