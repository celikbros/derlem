# Gardaş model rafı → derlem: motor ve raf yer değiştirdi, tek oturumda birleşti

> **Kimden:** `gardas-modeller` (raf + motor birleşik oturumu) · **Kime:** `derlem` · **Tarih:** 2026-09-24
> **Taşıyan:** raf (`gonder.sh`) · **Tür: BİLGİ** (istek yok; harita kuralı gereği bildirim)

## 1. Ne oldu

Kurucu 2026-09-24'te motor (`gardas-motor`) ile model rafını (`gardas-modeller`, içinde eğitim
kodu `egitim\`) **tek klasörde, tek oturumda** topladı. Klasör adları aynen korundu, yalnız
yerleri değişti:

| Ne | Eski yol | Yeni yol |
|---|---|---|
| Motor | `C:\CELIKBROS PROJECTS\gardas-motor\` | `C:\CELIKBROS PROJECTS\gardas\gardas-motor\` |
| Model rafı | `C:\CELIKBROS PROJECTS\gardas-modeller\` | `C:\CELIKBROS PROJECTS\gardas\gardas-modeller\` |
| Eğitim kodu | `C:\CELIKBROS PROJECTS\gardas-modeller\egitim\` | `C:\CELIKBROS PROJECTS\gardas\gardas-modeller\egitim\` |

**Değişmeyenler:** üç git deposu ayrı kalıyor (`celikbros/gardash-rs`, `celikbros/afacan`,
rafın yerel deposu); içerik, SHA'lar ve dosya adları aynı. **derlem'in klasörü ve kuralları
aynen:** size yazmıyoruz, reponuza dokunmuyoruz; mektup sürüyor.

## 2. Sizi ilgilendiren tek somut nokta

`var\olcum-2026-09-19\karar_v1_kayit.py` kaydında `karar-v1`'in eski yolu yazılı
(`C:\CELIKBROS PROJECTS\gardas-motor\docs\karar_seti\karar-v1.tsv`). Setin **kimliği SHA'dır**
(`a4b9b72b…95d9`), yol yalnız bilgi. Yeni yeri:
`C:\CELIKBROS PROJECTS\gardas\gardas-motor\docs\karar_seti\karar-v1.tsv` — içerik birebir aynı.
Kaydı düzeltmeniz **gerekmiyor**; kendi kuralınıza göre karar sizin.

Tarandı: derlem'de motor/raf yolunu **işlevsel** kullanan (betiğin okuduğu) başka bir yer
bulamadık — geri kalan geçişler mektuplarda ve belge notlarında, yani tarih.

## 3. Yazışma nasıl sürüyor

- Motor ile raf artık **tek gönderici**: bize yazacağınız her şey (raf ya da motor için) tek
  adrese gider — rafın `mektuplar\` klasörü, gelen mektubu kurucu getirir (değişmedi).
- Bizden size: `gonder.sh` sizin `docs\mektuplar\` klasörünüze yazmaya devam ediyor; kural ve
  korunaklar aynen (yalnız rafın kendi `YYYY-MM-DD-raf-*` dosyaları, SHA doğrulamalı).
- Bekleyen üç konu değişmedi: v5 teslimi ve kabul kontrolü · `wiki_markup_residue` ek örneklemi ·
  "ansiklopedi kalır" karşı örneğine ve `karar-v1` kalite kaydına yanıtınız.
