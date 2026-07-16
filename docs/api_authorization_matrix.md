# API Yetkilendirme Matrisi

**Tarih:** 2026-07-01
**Kapsam:** Derlem API veri okuma/yazma sınırları

Bu belge API yetkilendirmesinin kanonik rol sözleşmesidir. Uygulamadaki karşılığı
`internal/httpapi/authorization.go` dosyasındaki fail-closed route tablosudur.
Yeni bir veri endpoint'i açık rol listesi olmadan kaydedilemez.

## Roller

| Rol | Veri erişim sınırı |
|---|---|
| `admin` | Tüm operasyon çalışma alanları, release freeze ve artifact erişimi |
| `data_manager` | Kaynak yönetimi, işler, draft/frozen release ve artifact erişimi |
| `editor` | Kaynak çalışma alanı ve belge düzenleme; iş/release/benzerlik erişimi yok |
| `moderator` | Kaynak çalışma alanı, kaynak/belge/benzerlik incelemesi |
| `expert_reviewer` | Moderator ile aynı hassas inceleme erişimi |
| `contributor` | Şimdilik yalnız oturum bilgisi; katkı çalışma alanı v0.5'te açılacak |
| `consumer_team` | Yalnız frozen release metadata, manifest ve artifact erişimi |

## Endpoint Grupları

| API grubu | İzinli roller | Ek veri sınırı |
|---|---|---|
| `/api/v1/me` | Oturum açmış tüm roller | Yalnız aktif kullanıcının kimliği ve rolleri |
| Auth logout/logout-all | Oturum açmış tüm roller | Current veya tüm server session kayıtlarını revoke eder |
| Kullanıcı yönetimi (`/api/v1/users`) | Yalnız `admin` | Liste/oluşturma/rol/durum/parola; self-lockout ve son-aktif-admin koruması sunucuda; her değişiklik audit edilir |
| Kaynak katalogu/detayı | `admin`, `data_manager`, `editor`, `moderator`, `expert_reviewer` | Contributor ve consumer için kapalı |
| PII scan, belge örnekleri, kalite ve review geçmişi | `admin`, `data_manager`, `editor`, `moderator`, `expert_reviewer` | Ham/karantina metin aynı sınır içinde |
| Kaynak oluşturma ve upload | `admin`, `data_manager` | Yazma işlemi audit edilir |
| Sunucu yerel dosya ingest'i | Yalnız `admin` | Yol `IMPORT_ROOT` ile sınırlıdır; API ve worker ayrı ayrı doğrular |
| Kaynak metadata güncelleme | `admin`, `data_manager`, `editor` | Optimistic version kontrolü zorunlu |
| Belge içerik güncelleme | `admin`, `editor` | Yeni immutable nesne sürümü oluşturur |
| Kaynak/belge/benzerlik kararı | `admin`, `moderator`, `expert_reviewer` | Self-review ve kör review kuralları ayrıca uygulanır; belge kararı reviewer'a ait, süresi dolmamış claim gerektirir |
| Arka plan işleri | `admin`, `data_manager` | Job payload/result diğer rollere kapalıdır |
| Release liste/detay | `admin`, `data_manager`, `consumer_team` | Consumer yalnız `frozen` release görür; draft için `404` alır |
| Release oluşturma/export | `admin`, `data_manager` | Export yalnız frozen release için üretilir |
| Release freeze | `admin` | İnsan kritik kapısıdır |
| Frozen manifest/source/export indirme | `admin`, `data_manager`, `consumer_team` | Repository sorgusu ayrıca `release.status='frozen'` şartını zorlar |
| Benzerlik run/pair/tam metin | `admin`, `moderator`, `expert_reviewer` | Karar öncesi diğer reviewer kanıtları körlenir |

## Güvenlik Kuralları

- Kimlik yoksa `401`, rol yetersizse `403` döner.
- Consumer'a draft release varlığı sızdırılmaması için detay isteği `404` döner.
- Menü gizlemek güvenlik kontrolü değildir; asıl karar Go API'de verilir.
- `contributor` rolü için kaynak-sahipliği modeli kurulmadan genel kaynak okuma
  yetkisi verilmez.
- Multi-tenant/açık katkı öncesinde kaynak/proje bazlı ACL ayrıca `SEC-P1-02`
  kapsamında uygulanacaktır.

## Doğrulama

`internal/httpapi/authorization_test.go` tüm korumalı GET endpoint'lerini yedi
uygulama rolüne karşı pozitif ve negatif olarak sınar. Test ayrıca her korumalı
route'un boş olmayan ve bilinen rollerden oluşan bir politika taşımasını zorlar.

```powershell
go test ./internal/httpapi
```
