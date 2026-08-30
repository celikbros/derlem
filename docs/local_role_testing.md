# Local Rol Test Kullanıcıları

Bu belge yalnızca local geliştirme/test ortamı içindir. Production ortamında bu
hesaplar ve ortak parola kullanılmamalıdır.

## Hazır Local Hesaplar

Admin bootstrap hesabı:

| Rol | E-posta | Parola |
|---|---|---|
| admin | `admin@derlem.local` | `xRPCEKSW8WplQNuxKXy1` |

Local rol test hesapları:

| Rol | E-posta | Parola |
|---|---|---|
| data_manager | `manager@derlem.local` | `DerlemTest123!` |
| editor | `editor@derlem.local` | `DerlemTest123!` |
| moderator | `moderator@derlem.local` | `DerlemTest123!` |
| expert_reviewer | `expert@derlem.local` | `DerlemTest123!` |
| contributor | `contributor@derlem.local` | `DerlemTest123!` |
| consumer_team | `consumer@derlem.local` | `DerlemTest123!` |

## Test Matrisi

| Rol | Görmesi / yapabilmesi gerekenler |
|---|---|
| admin | Tüm kaynakları görür, kaynak oluşturur, metadata düzenler, dosya yükler, belge inceler, release oluşturur, release freeze eder, artifact indirir. |
| data_manager | Kaynak oluşturur, metadata düzenler, dosya yükler, release oluşturur ve artifact indirir; release freeze edemez. |
| editor | Kaynak metadata'sı ve belge içeriği düzenler; yeni kaynak oluşturamaz, release freeze edemez. |
| moderator | Kaynak/belge onay-ret-hassas kararlarını verir; metadata düzenleyemez, kaynak oluşturamaz. |
| expert_reviewer | Moderator gibi review kararı verir; özellikle hassas alan incelemesi için kullanılır. |
| contributor | Yalnız oturum açar; katkı çalışma alanı hazır olana kadar operasyon verisi veya kaynak katalogu göremez. |
| consumer_team | Yalnız frozen release ve artifact indirme akışını görür; draft release, kaynak/review ve iş verisine erişemez. |

## Tarayıcıdan Test Sırası

1. Sol alttan çıkış yap.
2. Login ekranındaki yerel test hesabı butonlarından birini seç veya yukarıdaki e-posta/parola ile yeniden giriş yap.
3. Sol altta görünen e-posta ve rol bilgisinin doğru olduğunu kontrol et.
4. Yalnız rol için gösterilen menüleri dolaş; görünmeyen menünün API'sine doğrudan istek atıldığında `403` bekle.
5. Rolüne göre beklenen butonların görünüp görünmediğini kontrol et.
6. Yetkisiz kullanıcıda write butonu görünmemeli; doğrudan API çağrısı yapılırsa backend `403` dönmelidir.

Kanonik endpoint/rol sınırları için
[`api_authorization_matrix.md`](api_authorization_matrix.md) belgesine bakın.

## Hızlı API Login Kontrolü

```powershell
$body = @{ email = "manager@derlem.local"; password = "DerlemTest123!" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri "http://localhost:18401/api/v1/auth/login" -ContentType "application/json" -Body $body
```
