// Rol tanımlarının tek kaynağı. Hem giriş ekranındaki yardım penceresi hem de
// uygulama içindeki Rehber (guide-panel) buradan okur; böylece iki yerdeki
// açıklamalar birbirinden ayrışmaz.

export type RoleInfo = {
  /** Kanonik API rolü (user.roles içindeki değer). */
  role: string;
  /** Giriş kartındaki kısa etiket (admin, manager, ...). */
  label: string;
  /** Başlık: "Yönetici (admin)". */
  title: string;
  /** Tek satırlık özet — giriş kartı ve hoş geldin ipucu bunu kullanır. */
  summary: string;
  /** "Kimdir?" — tek cümlelik kişi tarifi. */
  who: string;
  /** "Ne iş yapar?" — ayrıntılı görev listesi. */
  duties: string[];
};

export const ROLE_INFO: RoleInfo[] = [
  {
    role: "admin",
    label: "admin",
    title: "Yönetici (admin)",
    summary: "Yönetim: kullanıcılar, release freeze — tüm yetkiler",
    who: "Sistemin sahibi ve işleticisi.",
    duties: [
      "Tüm ekranları görür ve tüm işlemleri yapabilir.",
      "Yalnızca bu role açık iki kritik yetki: release freeze ve kontrollü yeniden örnekleme.",
      "Kullanıcı hesaplarını ve rolleri yönetir.",
    ],
  },
  {
    role: "data_manager",
    label: "manager",
    title: "Veri yöneticisi (data_manager)",
    summary: "Kaynak kaydı açma ve dosya yükleme",
    who: "Veriyi sisteme sokan kişi.",
    duties: [
      "Yeni kaynak kaydı açar, metadata ve hak bilgisini düzenler.",
      "Dosya yükler veya yerel ingest başlatır.",
      "Release taslağı oluşturur; manifest ve export indirir. Freeze edemez.",
    ],
  },
  {
    role: "editor",
    label: "editor",
    title: "Editör (editor)",
    summary: "Metadata ve belge içeriği düzeltme",
    who: "Metni ve künyeyi düzelten kişi.",
    duties: [
      "Kaynak metadata’sını düzenler.",
      "Belge içeriğini düzeltip yeni immutable sürüm oluşturur.",
      "Kaynak açamaz, onay kararı veremez.",
    ],
  },
  {
    role: "moderator",
    label: "moderator",
    title: "Moderatör (moderator)",
    summary: "Örnek inceleme ve kaynak onayı",
    who: "Kaynağı onaylayan inceleyici.",
    duties: [
      "İnceleme kuyruğundaki örnek belgeleri okur ve kalite puanı verir.",
      "Kaynak için onay, ret veya hassas inceleme kararı verir.",
      "Kendi yüklediği kaynağı onaylayamaz (self-review engeli).",
    ],
  },
  {
    role: "expert_reviewer",
    label: "expert",
    title: "Uzman inceleyici (expert_reviewer)",
    summary: "Hassas inceleme ve benzerlik etiketleme",
    who: "Hassas kararları ve benzerlik etiketlemesini yapan uzman.",
    duties: [
      "Moderatör ile aynı inceleme ve karar yetkilerine sahiptir.",
      "Benzerlik ekranında yakın-tekrar çiftlerini körlemeli olarak etiketler.",
    ],
  },
  {
    role: "contributor",
    label: "contributor",
    title: "Katkıcı (contributor)",
    summary: "Henüz işlem yok (katkı kuyruğu v0.5’te)",
    who: "Dış katkı sağlayacak kişi (yakında).",
    duties: [
      "Şimdilik yalnızca oturum açabilir; katkı kuyruğu v0.5 sürümünde planlıdır.",
    ],
  },
  {
    role: "consumer_team",
    label: "consumer",
    title: "Tüketici ekip (consumer_team)",
    summary: "Frozen release görüntüleme ve indirme",
    who: "Çıktıyı kullanan model/eğitim ekibi.",
    duties: [
      "Yalnızca donmuş (frozen) release’leri görür.",
      "Manifest, kaynak artifact’i ve JSONL/TXT export indirir; checksum ile doğrular.",
    ],
  },
];

/** Kanonik role göre arama (guide-panel için). */
export const roleInfoByRole: Record<string, RoleInfo> = Object.fromEntries(
  ROLE_INFO.map((info) => [info.role, info]),
);

/** Giriş etiketine göre kısa özet (giriş kartı ve hoş geldin ipucu için). */
export const roleSummaryByLabel: Record<string, string> = Object.fromEntries(
  ROLE_INFO.map((info) => [info.label, info.summary]),
);
